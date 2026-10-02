import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-secret-key-change-in-production-12345678')
    FERNET_KEY = os.environ.get('FERNET_KEY') or None
    
    # Ensure instance and storage folders exist
    (BASE_DIR / "instance").mkdir(parents=True, exist_ok=True)
    
    # Database
    db_env_url = os.environ.get('DATABASE_URL')
    if not db_env_url or db_env_url == 'sqlite:///instance/app.db':
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{BASE_DIR / "instance" / "app.db"}'
    else:
        # Render and older Heroku postgres URLs start with postgres://
        # SQLAlchemy 1.4+ requires postgresql://
        if db_env_url.startswith("postgres://"):
            db_env_url = db_env_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = db_env_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads & Storage (Strictly separated from web-accessible static directory)
    UPLOAD_FOLDER = Path(os.environ.get('UPLOAD_FOLDER', BASE_DIR / 'storage' / 'uploads')).resolve()
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 50 * 1024 * 1024))  # 50 MB
    MAX_STORAGE_PER_USER = int(os.environ.get('MAX_STORAGE_PER_USER_MB', 500)) * 1024 * 1024  # 500 MB in bytes

    # Allowed Upload File Extensions
    ALLOWED_EXTENSIONS = {
        'zip', 'tar', 'gz', 'py', 'js', 'html', 'css', 'json', 'md', 'txt',
        'pdf', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'csv', 'yaml', 'yml', 'xml'
    }

    # Session & Cookie Security
    SESSION_COOKIE_NAME = 'spm_session'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('PERMANENT_SESSION_LIFETIME', 3600))  # 1 hour

    # Flask-WTF CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Valid for lifetime of session

    # Flask-Limiter
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '200 per day; 50 per hour')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_STORAGE_URI = 'memory://'

    # Security Branding / TOTP Issuer
    TOTP_ISSUER_NAME = 'SecureProjectManager'

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    UPLOAD_FOLDER = BASE_DIR / 'storage' / 'test_uploads'
    SECRET_KEY = 'test-secret-key-very-secure-for-tests-only'
    # Test fernet key
    FERNET_KEY = 'gl65wnTcNSa426cgDS6Vj_Bxiv7twvuLtNkxiHkNqx0='
    RATELIMIT_ENABLED = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Strict'

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
