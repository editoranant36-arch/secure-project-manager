from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify
from flask_login import current_user

def two_factor_required(f):
    """
    Ensures that the user is logged in AND has completed 2FA verification.
    If 2FA is not yet enrolled, redirects to 2FA enrollment.
    If 2FA is enrolled but not yet verified for this session, redirects to 2FA verification.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'message': 'Authentication required'}), 401
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login', next=request.url))

        # Check if user has 2FA enabled
        if not current_user.mfa_enabled:
            # Force 2FA enrollment
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'MFA_REQUIRED', 'message': '2FA enrollment is required to access protected resources'}), 403
            flash('Two-Factor Authentication is required. Please set up your authenticator.', 'info')
            return redirect(url_for('auth.setup_2fa'))

        # Check if 2FA has been verified in the active session
        if not session.get('2fa_verified'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': '2FA_VERIFICATION_REQUIRED', 'message': '2FA verification required'}), 403
            flash('Please complete Two-Factor Authentication to access this area.', 'warning')
            return redirect(url_for('auth.verify_2fa', next=request.url))

        return f(*args, **kwargs)
    return decorated_function

def api_two_factor_required(f):
    """Decorator specifically for API endpoints returning JSON errors on 2FA failure."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'UNAUTHORIZED', 'message': 'Authentication required'}), 401
        
        if not current_user.mfa_enabled:
            return jsonify({'error': 'MFA_NOT_ENROLLED', 'message': '2FA must be enrolled to perform this operation'}), 403

        if not session.get('2fa_verified'):
            return jsonify({'error': 'MFA_VERIFICATION_REQUIRED', 'message': '2FA verification required'}), 403

        return f(*args, **kwargs)
    return decorated_function
