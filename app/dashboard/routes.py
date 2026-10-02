from flask import Blueprint, render_template, redirect, url_for, session, jsonify, request
from flask_login import current_user
from app.auth.decorators import two_factor_required, api_two_factor_required
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.models.audit_log import AuditLog
from app.models.user import User
from app.extensions import db
from flask import current_app

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
def landing():
    if current_user.is_authenticated and session.get('2fa_verified'):
        return redirect(url_for('dashboard.index'))
    return render_template('landing.html')

@dashboard_bp.route('/dashboard')
@two_factor_required
def index():
    projects_count = Project.query.filter_by(owner_id=current_user.id).count()
    
    # Calculate storage used
    storage_used = current_user.total_storage_used()
    quota_limit = current_app.config.get('MAX_STORAGE_PER_USER', 500 * 1024 * 1024)
    storage_percent = round((storage_used / quota_limit) * 100, 1) if quota_limit else 0

    # Total files
    total_files = ProjectFile.query.join(Project).filter(Project.owner_id == current_user.id).count()

    # Recent projects
    recent_projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.updated_at.desc()).limit(5).all()

    # Recent activity logs for this user
    recent_activity = AuditLog.query.filter_by(user_id=current_user.id).order_by(AuditLog.timestamp.desc()).limit(8).all()

    return render_template(
        'dashboard.html',
        projects_count=projects_count,
        storage_used=storage_used,
        quota_limit=quota_limit,
        storage_percent=storage_percent,
        total_files=total_files,
        recent_projects=recent_projects,
        recent_activity=recent_activity
    )

@dashboard_bp.route('/api/dashboard', methods=['GET'])
@api_two_factor_required
def api_dashboard():
    projects_count = Project.query.filter_by(owner_id=current_user.id).count()
    storage_used = current_user.total_storage_used()
    quota_limit = current_app.config.get('MAX_STORAGE_PER_USER', 500 * 1024 * 1024)
    storage_percent = round((storage_used / quota_limit) * 100, 1) if quota_limit else 0
    total_files = ProjectFile.query.join(Project).filter(Project.owner_id == current_user.id).count()

    recent_projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.updated_at.desc()).limit(5).all()
    recent_activity = AuditLog.query.filter_by(user_id=current_user.id).order_by(AuditLog.timestamp.desc()).limit(10).all()

    return jsonify({
        'success': True,
        'user': current_user.to_dict(),
        'metrics': {
            'projects_count': projects_count,
            'storage_used_bytes': storage_used,
            'quota_limit_bytes': quota_limit,
            'storage_percent': storage_percent,
            'total_files': total_files
        },
        'recent_projects': [p.to_dict() for p in recent_projects],
        'recent_activity': [a.to_dict() for a in recent_activity]
    }), 200

@dashboard_bp.route('/api/profile', methods=['GET'])
@api_two_factor_required
def api_profile():
    return jsonify({'success': True, 'profile': current_user.to_dict()}), 200

@dashboard_bp.route('/api/profile', methods=['PATCH'])
@api_two_factor_required
def api_update_profile():
    data = request.get_json(silent=True) or {}
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip().lower()

    if full_name:
        current_user.full_name = full_name
    if email and email != current_user.email:
        if User.query.filter(User.email == email, User.id != current_user.id).first():
            return jsonify({'error': 'EMAIL_EXISTS', 'message': 'Email is already taken'}), 409
        current_user.email = email

    db.session.commit()
    return jsonify({'success': True, 'profile': current_user.to_dict()}), 200
