from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import current_user
from app.extensions import db
from app.models.user import User
from app.models.session import SessionModel
from app.models.audit_log import AuditLog
from app.auth.decorators import two_factor_required, api_two_factor_required
from app.auth.services import log_audit_event, revoke_session, revoke_all_other_sessions
from app.auth.totp import generate_backup_codes
from app.auth.routes import is_password_strong

security_bp = Blueprint('security', __name__)

# ---------------- PROFILE ROUTES ----------------

@security_bp.route('/profile', methods=['GET', 'POST'])
@two_factor_required
def profile():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()

        if not full_name or not email:
            flash("Full name and email are required.", "danger")
            return render_template('profile.html', user=current_user)

        if email != current_user.email:
            existing = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing:
                flash("Email is already in use by another account.", "danger")
                return render_template('profile.html', user=current_user)
            current_user.email = email

        current_user.full_name = full_name
        db.session.commit()
        log_audit_event('PROFILE_UPDATE', 'SUCCESS', user_id=current_user.id, details="Updated profile details")
        flash("Profile updated successfully.", "success")
        return redirect(url_for('security.profile'))

    return render_template('profile.html', user=current_user)


@security_bp.route('/profile/password', methods=['POST'])
@two_factor_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "danger")
        log_audit_event('PASSWORD_CHANGE', 'FAILURE', user_id=current_user.id, details="Invalid current password provided")
        return redirect(url_for('security.profile'))

    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for('security.profile'))

    strong, msg = is_password_strong(new_password)
    if not strong:
        flash(msg, "danger")
        return redirect(url_for('security.profile'))

    current_user.set_password(new_password)
    db.session.commit()
    log_audit_event('PASSWORD_CHANGE', 'SUCCESS', user_id=current_user.id, details="Password changed successfully")
    flash("Password updated successfully.", "success")
    return redirect(url_for('security.profile'))


# ---------------- SECURITY SETTINGS ROUTES ----------------

@security_bp.route('/security')
@two_factor_required
def index():
    # Active sessions
    sessions = SessionModel.query.filter_by(
        user_id=current_user.id,
        revoked_at=None
    ).order_by(SessionModel.created_at.desc()).all()

    current_token = session.get('session_token')

    # Security activity logs
    activity_logs = AuditLog.query.filter_by(
        user_id=current_user.id
    ).order_by(AuditLog.timestamp.desc()).limit(20).all()

    return render_template(
        'security.html',
        user=current_user,
        sessions=sessions,
        current_token=current_token,
        activity_logs=activity_logs
    )


@security_bp.route('/security/backup-codes/regenerate', methods=['POST'])
@two_factor_required
def regenerate_backup_codes():
    password = request.form.get('password', '')
    if not current_user.check_password(password):
        flash("Incorrect password. Verification failed.", "danger")
        return redirect(url_for('security.index'))

    new_codes = generate_backup_codes(count=8)
    current_user.set_backup_codes(new_codes)
    db.session.commit()

    log_audit_event('BACKUP_CODES_REGENERATED', 'SUCCESS', user_id=current_user.id, details="Regenerated backup recovery codes")
    session['new_backup_codes'] = new_codes
    flash("New backup codes generated. Save them immediately.", "success")
    return redirect(url_for('auth.show_backup_codes'))


@security_bp.route('/security/2fa/re-enroll-request', methods=['POST'])
@two_factor_required
def request_re_enroll():
    password = request.form.get('password', '')
    if not current_user.check_password(password):
        flash("Incorrect password. Re-enrollment authentication failed.", "danger")
        return redirect(url_for('security.index'))

    session['re_enroll_allowed'] = True
    session.pop('enroll_totp_secret', None)
    log_audit_event('2FA_RE_ENROLL_INIT', 'SUCCESS', user_id=current_user.id, details="User initiated 2FA re-enrollment")
    return redirect(url_for('auth.setup_2fa'))


@security_bp.route('/security/sessions/<int:session_id>/revoke', methods=['POST'])
@two_factor_required
def revoke_session_route(session_id: int):
    if revoke_session(session_id, current_user.id):
        flash("Session revoked successfully.", "success")
    else:
        flash("Could not revoke session.", "danger")
    return redirect(url_for('security.index'))


@security_bp.route('/security/sessions/revoke-others', methods=['POST'])
@two_factor_required
def revoke_others_route():
    current_token = session.get('session_token')
    revoke_all_other_sessions(current_user.id, keep_token=current_token)
    flash("All other active sessions have been revoked.", "success")
    return redirect(url_for('security.index'))


# ---------------- RESTFUL API SECURITY ENDPOINTS ----------------

@security_bp.route('/api/security/status', methods=['GET'])
@api_two_factor_required
def api_security_status():
    active_sessions_count = SessionModel.query.filter_by(user_id=current_user.id, revoked_at=None).count()
    return jsonify({
        'success': True,
        'mfa_enabled': current_user.mfa_enabled,
        'backup_codes_remaining': current_user.remaining_backup_codes_count(),
        'active_sessions_count': active_sessions_count
    }), 200


@security_bp.route('/api/security/2fa/disable', methods=['POST'])
@api_two_factor_required
def api_disable_2fa():
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')

    if not current_user.check_password(password):
        log_audit_event('2FA_DISABLE', 'FAILURE', user_id=current_user.id, details="Failed password verification to disable 2FA")
        return jsonify({'error': 'INVALID_PASSWORD', 'message': 'Password verification failed'}), 401

    current_user.mfa_enabled = False
    current_user.encrypted_totp_secret = None
    current_user.backup_codes_hash = None
    db.session.commit()

    log_audit_event('2FA_DISABLE', 'SUCCESS', user_id=current_user.id, details="User disabled 2FA")
    return jsonify({'success': True, 'message': 'Two-Factor Authentication has been disabled'}), 200


@security_bp.route('/api/security/2fa/re-enroll', methods=['POST'])
@api_two_factor_required
def api_re_enroll():
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')

    if not current_user.check_password(password):
        return jsonify({'error': 'INVALID_PASSWORD', 'message': 'Password verification failed'}), 401

    session['re_enroll_allowed'] = True
    session.pop('enroll_totp_secret', None)
    return jsonify({'success': True, 'message': 'Re-enrollment unlocked. Call /api/2fa/enroll next.'}), 200


@security_bp.route('/api/security/sessions', methods=['GET'])
@api_two_factor_required
def api_get_sessions():
    sessions = SessionModel.query.filter_by(user_id=current_user.id, revoked_at=None).order_by(SessionModel.created_at.desc()).all()
    current_token = session.get('session_token')
    
    session_list = []
    for s in sessions:
        item = s.to_dict()
        item['is_current'] = (s.session_token == current_token)
        session_list.append(item)

    return jsonify({'success': True, 'sessions': session_list}), 200


@security_bp.route('/api/security/sessions/<int:session_id>', methods=['DELETE'])
@api_two_factor_required
def api_revoke_session(session_id: int):
    if revoke_session(session_id, current_user.id):
        return jsonify({'success': True, 'message': f'Session {session_id} revoked'}), 200
    return jsonify({'error': 'NOT_FOUND', 'message': 'Session not found or already revoked'}), 404


@security_bp.route('/api/security/activity', methods=['GET'])
@api_two_factor_required
def api_get_activity():
    limit = request.args.get('limit', 20, type=int)
    logs = AuditLog.query.filter_by(user_id=current_user.id).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return jsonify({'success': True, 'activity': [l.to_dict() for l in logs]}), 200
