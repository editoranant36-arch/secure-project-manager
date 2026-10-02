import pytest
from app.models.user import User

def test_user_registration(client, app):
    response = client.post('/register', data={
        'full_name': 'David Miller',
        'username': 'davidm',
        'email': 'david@example.com',
        'password': 'StrongPassword123!',
        'confirm_password': 'StrongPassword123!',
        'terms': 'on'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username='davidm').first()
        assert user is not None
        assert user.full_name == 'David Miller'
        assert user.check_password('StrongPassword123!') is True
        assert user.check_password('WrongPassword') is False

def test_registration_weak_password_rejected(client, app):
    response = client.post('/register', data={
        'full_name': 'Weak User',
        'username': 'weakuser',
        'email': 'weak@example.com',
        'password': '123',
        'confirm_password': '123',
        'terms': 'on'
    }, follow_redirects=True)

    assert b"Password must be at least 8 characters long" in response.data

def test_registration_duplicate_username_rejected(client, test_user):
    response = client.post('/register', data={
        'full_name': 'Duplicate User',
        'username': test_user.username,
        'email': 'different@example.com',
        'password': 'StrongPassword123!',
        'confirm_password': 'StrongPassword123!',
        'terms': 'on'
    }, follow_redirects=True)

    assert b"already exists" in response.data

def test_login_invalid_password_rejected(client, test_user):
    response = client.post('/login', data={
        'identifier': test_user.username,
        'password': 'IncorrectPassword999!'
    }, follow_redirects=True)

    assert b"Invalid username/email or password" in response.data

def test_login_redirects_to_2fa_setup_if_not_enrolled(client, test_user):
    response = client.post('/login', data={
        'identifier': test_user.username,
        'password': 'SecurePass123!@#'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert '/setup-2fa' in response.location

def test_login_redirects_to_2fa_verify_if_enrolled(client, test_user_with_2fa):
    response = client.post('/login', data={
        'identifier': test_user_with_2fa.username,
        'password': 'SecurePass123!@#'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert '/verify-2fa' in response.location

def test_logout_clears_session(client, test_user_with_2fa):
    # Log in first
    client.post('/login', data={
        'identifier': test_user_with_2fa.username,
        'password': 'SecurePass123!@#'
    })
    
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b"You have been securely logged out" in response.data

    with client.session_transaction() as sess:
        assert '2fa_verified' not in sess
        assert 'user_id' not in sess
