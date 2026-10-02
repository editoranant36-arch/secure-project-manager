import secrets
from datetime import datetime, timedelta, timezone
from flask import session, request, current_app
from app.extensions import db
from app.models.user import User
from app.models.session import SessionModel
from app.models.audit_log import AuditLog

def get_client_ip() -> str:
    """Safely obtain client IP address handling proxies."""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(",")[0].strip()
    return request.remote_addr or '127.0.0.1'

def log_audit_event(event_type: str, outcome: str, user_id: int | None = None, details: str | None = None):
    """
    Record an audit log entry.
    Strictly guarantees NO passwords, OTPs, or secret keys are logged.
    """
    try:
        ip = get_client_ip()
        log = AuditLog(
            user_id=user_id,
            event_type=event_type,
            ip_address=ip,
            timestamp=datetime.now(timezone.utc),
            outcome=outcome,
            details=details[:500] if details else None
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Audit log recording error: {e}")

def create_user_session(user: User) -> SessionModel:
    """Create a tracked database session for the user and store token in Flask session."""
    token = secrets.token_urlsafe(64)
    lifetime = current_app.config.get('PERMANENT_SESSION_LIFETIME', 3600)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=lifetime)
    
    user_session = SessionModel(
        user_id=user.id,
        session_token=token,
        ip_address=get_client_ip(),
        user_agent=request.user_agent.string[:250] if request.user_agent else 'Unknown',
        created_at=now,
        expires_at=expires
    )
    db.session.add(user_session)
    db.session.commit()

    # Store in flask session
    session['session_token'] = token
    session['user_id'] = user.id
    return user_session

def rotate_session_token(user: User):
    """Rotate session token to prevent session fixation attacks."""
    # Revoke old session if exists
    old_token = session.get('session_token')
    if old_token:
        old_session = SessionModel.query.filter_by(session_token=old_token).first()
        if old_session:
            old_session.revoked_at = datetime.now(timezone.utc)
    
    # Create fresh session
    create_user_session(user)

def revoke_session(session_id: int, user_id: int) -> bool:
    """Revoke a specific session for a user."""
    s = SessionModel.query.filter_by(id=session_id, user_id=user_id).first()
    if s and not s.revoked_at:
        s.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        log_audit_event('SESSION_REVOKE', 'SUCCESS', user_id=user_id, details=f"Revoked session {session_id}")
        return True
    return False

def revoke_all_other_sessions(user_id: int, keep_token: str | None = None):
    """Revoke all sessions for a user except the currently active one."""
    query = SessionModel.query.filter_by(user_id=user_id, revoked_at=None)
    if keep_token:
        query = query.filter(SessionModel.session_token != keep_token)
    
    for s in query.all():
        s.revoked_at = datetime.now(timezone.utc)
    db.session.commit()
    log_audit_event('SESSION_REVOKE_OTHERS', 'SUCCESS', user_id=user_id, details="Revoked all other active sessions")
