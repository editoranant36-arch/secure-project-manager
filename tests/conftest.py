import os
import shutil
import tempfile
import pytest
import pyotp
from pathlib import Path
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.project import Project
from app.auth.totp import generate_totp_secret, generate_backup_codes

@pytest.fixture
def app():
    # Create temporary storage directory for tests
    temp_dir = tempfile.mkdtemp()
    
    app = create_app('testing')
    app.config.update({
        'UPLOAD_FOLDER': Path(temp_dir),
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'RATELIMIT_ENABLED': False
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

    # Cleanup temp upload directory
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def test_user(app):
    with app.app_context():
        user = User(
            full_name="Alice Smith",
            username="alicesmith",
            email="alice@example.com",
            mfa_enabled=False
        )
        user.set_password("SecurePass123!@#")
        db.session.add(user)
        db.session.commit()
        return User.query.get(user.id)

@pytest.fixture
def test_user_with_2fa(app):
    with app.app_context():
        secret = pyotp.random_base32()
        user = User(
            full_name="Bob Jones",
            username="bobjones",
            email="bob@example.com",
            mfa_enabled=True
        )
        user.set_password("SecurePass123!@#")
        user.set_totp_secret(secret)
        user.set_backup_codes(["RECO-VERY", "TEST-CODE"])
        db.session.add(user)
        db.session.commit()
        return User.query.get(user.id)

@pytest.fixture
def test_user_2(app):
    with app.app_context():
        secret = pyotp.random_base32()
        user = User(
            full_name="Charlie Dave",
            username="charliedave",
            email="charlie@example.com",
            mfa_enabled=True
        )
        user.set_password("SecurePass123!@#")
        user.set_totp_secret(secret)
        db.session.add(user)
        db.session.commit()
        return User.query.get(user.id)
