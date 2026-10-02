import os
from flask import Flask, render_template, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import config_by_name
from app.extensions import db, login_manager, csrf, limiter, migrate
from app.models.user import User

def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))

    # Ensure required directories exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)

    # Exempt /api/ routes from CSRF to allow REST client testing
    csrf.exempt('app.auth.routes.api_register')
    csrf.exempt('app.auth.routes.api_login')
    csrf.exempt('app.auth.routes.api_2fa_enroll')
    csrf.exempt('app.auth.routes.api_2fa_verify_enrollment')
    csrf.exempt('app.auth.routes.api_2fa_verify_login')
    csrf.exempt('app.auth.routes.api_logout')
    csrf.exempt('app.auth.routes.api_password_change')
    csrf.exempt('app.auth.routes.api_password_reset')
    csrf.exempt('app.projects.routes.api_create_project')
    csrf.exempt('app.projects.routes.api_update_project')
    csrf.exempt('app.projects.routes.api_delete_project')
    csrf.exempt('app.projects.routes.api_upload_project_file')
    csrf.exempt('app.projects.routes.api_create_version')
    csrf.exempt('app.dashboard.routes.api_update_profile')
    csrf.exempt('app.security.routes.api_disable_2fa')
    csrf.exempt('app.security.routes.api_re_enroll')
    csrf.exempt('app.security.routes.api_revoke_session')

    # Flask-Login user loader
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from app.auth import auth_bp
    from app.projects import projects_bp
    from app.dashboard import dashboard_bp
    from app.security import security_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(security_bp)

    # Custom template filters
    @app.template_filter('filesizeformat')
    def filter_filesizeformat(value):
        if value is None:
            return '0 B'
        bytes_val = float(value)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}" if unit != 'B' else f"{int(bytes_val)} B"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} TB"

    @app.template_filter('datetimeformat')
    def filter_datetimeformat(dt, fmt='%b %d, %Y %H:%M'):
        if not dt:
            return '-'
        return dt.strftime(fmt)

    # Security Headers Middleware
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
        
        # CSP allowing Bootstrap 5, FontAwesome, BoxIcons, Google Fonts
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        response.headers['Content-Security-Policy'] = csp

        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        return response

    # Global Error Handlers
    @app.errorhandler(400)
    def bad_request(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'BAD_REQUEST', 'message': str(e)}), 400
        return render_template('error.html', code=400, title="Bad Request", message="The request could not be processed."), 400

    @app.errorhandler(403)
    def forbidden(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'FORBIDDEN', 'message': 'Access forbidden'}), 403
        return render_template('error.html', code=403, title="Access Forbidden", message="You do not have permission to view this resource."), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'NOT_FOUND', 'message': 'Resource not found'}), 404
        return render_template('error.html', code=404, title="Not Found", message="The requested page or resource could not be found."), 404

    @app.errorhandler(413)
    def request_entity_too_large(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'PAYLOAD_TOO_LARGE', 'message': 'File size exceeds server limit'}), 413
        return render_template('error.html', code=413, title="File Too Large", message="Uploaded file exceeds the maximum allowed upload size (50MB)."), 413

    @app.errorhandler(429)
    def ratelimit_handler(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'TOO_MANY_REQUESTS', 'message': 'Rate limit exceeded. Please wait a moment.'}), 429
        return render_template('error.html', code=429, title="Rate Limit Exceeded", message="Too many requests. For security reasons, please slow down."), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'INTERNAL_ERROR', 'message': 'An unexpected server error occurred'}), 500
        return render_template('error.html', code=500, title="Server Error", message="An unexpected error occurred. Our team has been notified."), 500

    # Reverse proxy support (for Render, Cloudflare, Nginx HTTPS headers)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    return app
