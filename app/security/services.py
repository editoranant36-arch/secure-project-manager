from app.models.session import SessionModel
from app.models.audit_log import AuditLog
from app.auth.services import revoke_session, revoke_all_other_sessions
from app.extensions import db

def get_user_security_overview(user_id: int) -> dict:
    """Compile security overview for user dashboard and security center."""
    active_sessions = SessionModel.query.filter_by(user_id=user_id, revoked_at=None).count()
    recent_activity = AuditLog.query.filter_by(user_id=user_id).order_by(AuditLog.timestamp.desc()).limit(10).all()

    return {
        'active_sessions_count': active_sessions,
        'recent_activity': recent_activity
    }

def get_active_sessions(user_id: int):
    """Retrieve all active sessions for a user."""
    return SessionModel.query.filter_by(
        user_id=user_id,
        revoked_at=None
    ).order_by(SessionModel.created_at.desc()).all()
