import json
from datetime import datetime, timezone
from flask import current_app
from flask_login import UserMixin
from cryptography.fernet import Fernet
import werkzeug.security
from app.extensions import db

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
    USE_ARGON2 = True
except ImportError:
    USE_ARGON2 = False


def _get_fernet():
    key = current_app.config.get('FERNET_KEY')
    if not key:
        # Fallback for dev if not set: generate deterministic key from secret_key
        import base64
        import hashlib
        raw = hashlib.sha256(current_app.config['SECRET_KEY'].encode()).digest()
        key = base64.urlsafe_b64encode(raw)
    elif isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(64), unique=True, index=True, nullable=False)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    encrypted_totp_secret = db.Column(db.Text, nullable=True)
    mfa_enabled = db.Column(db.Boolean, default=False, nullable=False)
    backup_codes_hash = db.Column(db.Text, nullable=True)  # JSON-encoded array of hashed backup codes
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    projects = db.relationship('Project', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    sessions = db.relationship('SessionModel', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')

    def set_password(self, password: str):
        if USE_ARGON2:
            self.password_hash = _hasher.hash(password)
        else:
            self.password_hash = werkzeug.security.generate_password_hash(password, method='scrypt')

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        if USE_ARGON2 and self.password_hash.startswith('$argon2'):
            try:
                valid = _hasher.verify(self.password_hash, password)
                if _hasher.check_needs_rehash(self.password_hash):
                    self.set_password(password)
                    db.session.commit()
                return valid
            except VerifyMismatchError:
                return False
            except Exception:
                return False
        # Fallback to werkzeug check
        return werkzeug.security.check_password_hash(self.password_hash, password)

    def set_totp_secret(self, secret: str):
        """Encrypt TOTP secret using Fernet before persisting to database."""
        if not secret:
            self.encrypted_totp_secret = None
            return
        f = _get_fernet()
        self.encrypted_totp_secret = f.encrypt(secret.encode()).decode()

    def get_totp_secret(self) -> str | None:
        """Decrypt TOTP secret at runtime."""
        if not self.encrypted_totp_secret:
            return None
        f = _get_fernet()
        try:
            return f.decrypt(self.encrypted_totp_secret.encode()).decode()
        except Exception:
            return None

    def set_backup_codes(self, plain_codes: list[str]):
        """Hash backup codes with SHA-256 for secure verification."""
        import hashlib
        hashed_codes = [hashlib.sha256(c.strip().upper().encode()).hexdigest() for c in plain_codes]
        self.backup_codes_hash = json.dumps(hashed_codes)

    def verify_and_consume_backup_code(self, candidate_code: str) -> bool:
        """Verify single-use backup recovery code and consume it if valid."""
        import hashlib
        if not self.backup_codes_hash:
            return False
        try:
            codes = json.loads(self.backup_codes_hash)
        except Exception:
            return False

        h = hashlib.sha256(candidate_code.strip().upper().encode()).hexdigest()
        if h in codes:
            codes.remove(h)
            self.backup_codes_hash = json.dumps(codes)
            db.session.commit()
            return True
        return False

    def remaining_backup_codes_count(self) -> int:
        if not self.backup_codes_hash:
            return 0
        try:
            return len(json.loads(self.backup_codes_hash))
        except Exception:
            return 0

    def total_storage_used(self) -> int:
        """Compute total storage used by user across all projects in bytes."""
        total = 0
        for project in self.projects:
            for file in project.files:
                total += (file.file_size or 0)
        return total

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'username': self.username,
            'email': self.email,
            'mfa_enabled': self.mfa_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'total_storage_used': self.total_storage_used(),
            'backup_codes_remaining': self.remaining_backup_codes_count()
        }

    def __repr__(self):
        return f'<User {self.username}>'
