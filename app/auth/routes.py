import re
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    session, jsonify, current_app
)
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db, limiter
from app.models.user import User
from app.models.session import SessionModel
from app.auth.totp import (
    generate_totp_secret, get_totp_uri, generate_qr_code_base64,
    verify_totp, generate_backup_codes
)
from app.auth.services import (
    log_audit_event, create_user_session, rotate_session_token,
    revoke_session, revoke_all_other_sessions
)
from app.auth.decorators import two_factor_required

auth_bp = Blueprint('auth', __name__)

def is_password_strong(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one digit."
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character."
    return True, ""


# ---------------- WEB INTERFACE ROUTES ----------------

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("15 per minute")
def register():
    if current_user.is_authenticated and session.get('2fa_verified'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        terms = request.form.get('terms')

        # Validations
        if not (full_name and username and email and password):
            flash("All fields are required.", "danger")
            return render_template('register.html', full_name=full_name, username=username, email=email)

        if not terms:
            flash("You must agree to the Terms and Conditions.", "warning")
            return render_template('register.html', full_name=full_name, username=username, email=email)

        if not re.match(r'^[a-zA-Z0-9_.-]{3,30}$', username):
            flash("Username must be between 3 and 30 characters and contain only letters, numbers, dots, hyphens, or underscores.", "danger")
            return render_template('register.html', full_name=full_name, email=email)

        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash("Please enter a valid email address.", "danger")
            return render_template('register.html', full_name=full_name, username=username)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('register.html', full_name=full_name, username=username, email=email)

        strong, msg = is_password_strong(password)
        if not strong:
            flash(msg, "danger")
            return render_template('register.html', full_name=full_name, username=username, email=email)

        # Check existing user
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("An account with that username or email already exists.", "danger")
            return render_template('register.html', full_name=full_name)

        # Create user
        user = User(
            full_name=full_name,
            username=username,
            email=email,
            mfa_enabled=False
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        log_audit_event('REGISTER', 'SUCCESS', user_id=user.id, details=f"User registered: {username}")
        flash("Registration successful! Please log in to complete your Two-Factor Authentication setup.", "success")
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated and session.get('2fa_verified'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not identifier or not password:
            flash("Username/email and password are required.", "danger")
            return render_template('login.html', identifier=identifier)

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()

        if not user or not user.check_password(password):
            log_audit_event('LOGIN_PASSWORD', 'FAILURE', user_id=user.id if user else None, details=f"Failed login attempt for identifier: {identifier}")
            flash("Invalid username/email or password.", "danger")
            return render_template('login.html', identifier=identifier)

        # Password verified! Log into Flask-Login with restricted state
        login_user(user, remember=remember)
        session['2fa_verified'] = False
        session['pending_2fa'] = True
        session['user_id'] = user.id
        create_user_session(user)

        log_audit_event('LOGIN_PASSWORD', 'SUCCESS', user_id=user.id, details="Primary credentials verified. Awaiting 2FA.")

        if user.mfa_enabled:
            return redirect(url_for('auth.verify_2fa'))
        else:
            flash("Two-Factor Authentication is required. Please scan the QR code to set up your authenticator app.", "info")
            return redirect(url_for('auth.setup_2fa'))

    return render_template('login.html')


@auth_bp.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    # If already verified and MFA enabled, only allow re-enrollment from security page
    if current_user.mfa_enabled and session.get('2fa_verified') and not session.get('re_enroll_allowed'):
        flash("Two-Factor Authentication is already enabled on your account.", "info")
        return redirect(url_for('security.index'))

    if request.method == 'GET':
        # Generate or retrieve secret for enrollment
        if 'enroll_totp_secret' not in session:
            session['enroll_totp_secret'] = generate_totp_secret()
        secret = session['enroll_totp_secret']
        uri = get_totp_uri(secret, current_user.username)
        qr_code = generate_qr_code_base64(uri)
        return render_template('setup_2fa.html', secret=secret, qr_code=qr_code, user=current_user)

    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        secret = session.get('enroll_totp_secret')

        if not secret:
            flash("Enrollment session expired. Please try again.", "warning")
            return redirect(url_for('auth.setup_2fa'))

        if not verify_totp(secret, otp_code, user_id=current_user.id):
            log_audit_event('2FA_ENROLL', 'FAILURE', user_id=current_user.id, details="Invalid OTP code during enrollment")
            flash("Invalid 6-digit verification code. Please make sure your device clock is synchronized and try again.", "danger")
            uri = get_totp_uri(secret, current_user.username)
            qr_code = generate_qr_code_base64(uri)
            return render_template('setup_2fa.html', secret=secret, qr_code=qr_code, user=current_user)

        # Successful enrollment
        current_user.set_totp_secret(secret)
        current_user.mfa_enabled = True

        # Generate fresh backup recovery codes
        backup_codes = generate_backup_codes(count=8)
        current_user.set_backup_codes(backup_codes)
        db.session.commit()

        # Update session states
        session.pop('enroll_totp_secret', None)
        session.pop('re_enroll_allowed', None)
        session['2fa_verified'] = True
        session['pending_2fa'] = False
        rotate_session_token(current_user)

        log_audit_event('2FA_ENROLL', 'SUCCESS', user_id=current_user.id, details="2FA enrollment completed and backup codes generated")
        
        # Save backup codes temporarily in session to present once to the user
        session['new_backup_codes'] = backup_codes
        flash("2FA successfully enabled! Please save your backup recovery codes in a safe place.", "success")
        return redirect(url_for('auth.show_backup_codes'))


@auth_bp.route('/backup-codes')
@two_factor_required
def show_backup_codes():
    codes = session.pop('new_backup_codes', None)
    if not codes:
        flash("Backup codes are only displayed once upon generation.", "info")
        return redirect(url_for('dashboard.index'))
    return render_template('backup_codes.html', backup_codes=codes)


@auth_bp.route('/verify-2fa', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def verify_2fa():
    if not current_user.is_authenticated:
        flash("Please log in first.", "warning")
        return redirect(url_for('auth.login'))

    if session.get('2fa_verified'):
        return redirect(url_for('dashboard.index'))

    if not current_user.mfa_enabled:
        return redirect(url_for('auth.setup_2fa'))

    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        backup_code = request.form.get('backup_code', '').strip()
        next_url = request.args.get('next') or url_for('dashboard.index')

        secret = current_user.get_totp_secret()
        success = False
        method_used = "TOTP"

        if otp_code:
            if verify_totp(secret, otp_code, user_id=current_user.id):
                success = True
        elif backup_code:
            if current_user.verify_and_consume_backup_code(backup_code):
                success = True
                method_used = "BACKUP_CODE"

        if success:
            session['2fa_verified'] = True
            session['pending_2fa'] = False
            rotate_session_token(current_user)
            log_audit_event('LOGIN_2FA', 'SUCCESS', user_id=current_user.id, details=f"2FA verified via {method_used}")
            flash("Two-Factor Authentication verified successfully.", "success")
            return redirect(next_url)
        else:
            log_audit_event('LOGIN_2FA', 'FAILURE', user_id=current_user.id, details="Invalid 2FA code or backup code submitted")
            flash("Invalid or expired 2FA code. If using an authenticator app, ensure your device time is synchronized.", "danger")
            return render_template('verify_2fa.html')

    return render_template('verify_2fa.html')


@auth_bp.route('/logout')
def logout():
    user_id = current_user.id if current_user.is_authenticated else None
    token = session.get('session_token')
    if token:
        s = SessionModel.query.filter_by(session_token=token).first()
        if s:
            from datetime import datetime, timezone
            s.revoked_at = datetime.now(timezone.utc)
            db.session.commit()

    if user_id:
        log_audit_event('LOGOUT', 'SUCCESS', user_id=user_id, details="User initiated logout")

    logout_user()
    session.clear()
    flash("You have been securely logged out.", "success")
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        log_audit_event('PASSWORD_RESET_REQUEST', 'SUCCESS' if user else 'WARNING', user_id=user.id if user else None, details=f"Password reset requested for {email}")
        # Always return generic message to avoid email enumeration
        flash("If that email address exists in our database, password reset instructions have been sent.", "info")
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')


# ---------------- RESTFUL API ENDPOINTS ----------------

@auth_bp.route('/api/register', methods=['POST'])
@limiter.limit("10 per minute")
def api_register():
    data = request.get_json(silent=True) or {}
    full_name = data.get('full_name', '').strip()
    username = data.get('username', '').strip().lower()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not (full_name and username and email and password):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'All fields are required'}), 400

    strong, msg = is_password_strong(password)
    if not strong:
        return jsonify({'error': 'WEAK_PASSWORD', 'message': msg}), 400

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'error': 'USER_EXISTS', 'message': 'Username or email already registered'}), 409

    user = User(full_name=full_name, username=username, email=email, mfa_enabled=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    log_audit_event('API_REGISTER', 'SUCCESS', user_id=user.id, details=f"API registration for {username}")
    return jsonify({'success': True, 'message': 'User registered successfully. Proceed to login and 2FA enrollment.', 'user_id': user.id}), 201


@auth_bp.route('/api/login', methods=['POST'])
@limiter.limit("10 per minute")
def api_login():
    data = request.get_json(silent=True) or {}
    identifier = data.get('identifier', '').strip().lower()
    password = data.get('password', '')

    if not identifier or not password:
        return jsonify({'error': 'MISSING_CREDENTIALS', 'message': 'Username/email and password required'}), 400

    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
    if not user or not user.check_password(password):
        log_audit_event('API_LOGIN_PASSWORD', 'FAILURE', user_id=user.id if user else None, details=f"Failed API login for {identifier}")
        return jsonify({'error': 'INVALID_CREDENTIALS', 'message': 'Invalid username or password'}), 401

    login_user(user)
    session['2fa_verified'] = False
    session['pending_2fa'] = True
    session['user_id'] = user.id
    user_session = create_user_session(user)

    log_audit_event('API_LOGIN_PASSWORD', 'SUCCESS', user_id=user.id, details="Password verified via API. Pending 2FA.")

    return jsonify({
        'success': True,
        'message': 'Primary authentication successful. 2FA verification required.',
        'mfa_enabled': user.mfa_enabled,
        'status': 'MFA_PENDING' if user.mfa_enabled else 'MFA_ENROLLMENT_REQUIRED',
        'session_token': user_session.session_token
    }), 200


@auth_bp.route('/api/2fa/enroll', methods=['POST'])
@login_required
def api_2fa_enroll():
    secret = generate_totp_secret()
    session['enroll_totp_secret'] = secret
    uri = get_totp_uri(secret, current_user.username)
    qr_code = generate_qr_code_base64(uri)

    return jsonify({
        'success': True,
        'secret': secret,
        'provisioning_uri': uri,
        'qr_code_data_uri': qr_code
    }), 200


@auth_bp.route('/api/2fa/verify-enrollment', methods=['POST'])
@login_required
def api_2fa_verify_enrollment():
    data = request.get_json(silent=True) or {}
    otp_code = data.get('otp_code', '').strip()
    secret = session.get('enroll_totp_secret')

    if not secret:
        return jsonify({'error': 'NO_PENDING_ENROLLMENT', 'message': 'Call /api/2fa/enroll first'}), 400

    if not verify_totp(secret, otp_code, user_id=current_user.id):
        log_audit_event('API_2FA_ENROLL', 'FAILURE', user_id=current_user.id, details="Invalid OTP code during API enrollment")
        return jsonify({'error': 'INVALID_OTP', 'message': 'Invalid 6-digit OTP code'}), 400

    current_user.set_totp_secret(secret)
    current_user.mfa_enabled = True
    backup_codes = generate_backup_codes(count=8)
    current_user.set_backup_codes(backup_codes)
    db.session.commit()

    session.pop('enroll_totp_secret', None)
    session['2fa_verified'] = True
    session['pending_2fa'] = False
    rotate_session_token(current_user)

    log_audit_event('API_2FA_ENROLL', 'SUCCESS', user_id=current_user.id, details="2FA enrollment completed via API")

    return jsonify({
        'success': True,
        'message': '2FA successfully activated',
        'backup_codes': backup_codes
    }), 200


@auth_bp.route('/api/2fa/verify-login', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_2fa_verify_login():
    data = request.get_json(silent=True) or {}
    otp_code = data.get('otp_code', '').strip()
    backup_code = data.get('backup_code', '').strip()

    if not current_user.mfa_enabled:
        return jsonify({'error': 'MFA_NOT_ENABLED', 'message': '2FA is not enabled for this user'}), 400

    secret = current_user.get_totp_secret()
    success = False
    method = 'TOTP'

    if otp_code:
        if verify_totp(secret, otp_code, user_id=current_user.id):
            success = True
    elif backup_code:
        if current_user.verify_and_consume_backup_code(backup_code):
            success = True
            method = 'BACKUP_CODE'

    if success:
        session['2fa_verified'] = True
        session['pending_2fa'] = False
        rotate_session_token(current_user)
        log_audit_event('API_LOGIN_2FA', 'SUCCESS', user_id=current_user.id, details=f"2FA verified via {method} API")
        return jsonify({'success': True, 'message': 'Authentication completed successfully', 'user': current_user.to_dict()}), 200

    log_audit_event('API_LOGIN_2FA', 'FAILURE', user_id=current_user.id, details="Invalid 2FA code in API call")
    return jsonify({'error': 'INVALID_2FA_CODE', 'message': 'Invalid OTP or backup recovery code'}), 401


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    user_id = current_user.id if current_user.is_authenticated else None
    token = session.get('session_token')
    if token:
        s = SessionModel.query.filter_by(session_token=token).first()
        if s:
            from datetime import datetime, timezone
            s.revoked_at = datetime.now(timezone.utc)
            db.session.commit()
    if user_id:
        log_audit_event('API_LOGOUT', 'SUCCESS', user_id=user_id, details="API logout")

    logout_user()
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200


@auth_bp.route('/api/password/change', methods=['POST'])
@two_factor_required
def api_password_change():
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_user.check_password(current_password):
        log_audit_event('PASSWORD_CHANGE', 'FAILURE', user_id=current_user.id, details="Incorrect current password provided")
        return jsonify({'error': 'INVALID_PASSWORD', 'message': 'Current password is incorrect'}), 400

    strong, msg = is_password_strong(new_password)
    if not strong:
        return jsonify({'error': 'WEAK_PASSWORD', 'message': msg}), 400

    current_user.set_password(new_password)
    db.session.commit()
    log_audit_event('PASSWORD_CHANGE', 'SUCCESS', user_id=current_user.id, details="Password updated successfully")
    return jsonify({'success': True, 'message': 'Password updated successfully'}), 200


@auth_bp.route('/api/password/reset', methods=['POST'])
def api_password_reset():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()
    log_audit_event('API_PASSWORD_RESET', 'SUCCESS' if user else 'WARNING', user_id=user.id if user else None, details=f"Password reset requested for {email}")
    return jsonify({'success': True, 'message': 'If the email exists, instructions have been dispatched'}), 200
