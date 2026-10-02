import pyotp
from app.models.user import User
from app.auth.totp import verify_totp

def test_2fa_enrollment_flow(client, test_user, app):
    # Log in user
    client.post('/login', data={
        'identifier': test_user.username,
        'password': 'SecurePass123!@#'
    })

    # Get setup page to establish secret
    setup_page = client.get('/setup-2fa')
    assert setup_page.status_code == 200
    assert b"Link Your Authenticator" in setup_page.data

    with client.session_transaction() as sess:
        secret = sess.get('enroll_totp_secret')
        assert secret is not None

    # Generate valid OTP code
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    # Submit valid code
    post_res = client.post('/setup-2fa', data={'otp_code': valid_code}, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"Emergency Backup Recovery Codes" in post_res.data

    with app.app_context():
        u = User.query.get(test_user.id)
        assert u.mfa_enabled is True
        assert u.get_totp_secret() == secret
        assert u.remaining_backup_codes_count() == 8

def test_2fa_enrollment_invalid_code_rejected(client, test_user, app):
    client.post('/login', data={
        'identifier': test_user.username,
        'password': 'SecurePass123!@#'
    })
    client.get('/setup-2fa')

    response = client.post('/setup-2fa', data={'otp_code': '000000'}, follow_redirects=True)
    assert b"Invalid 6-digit verification code" in response.data

    with app.app_context():
        u = User.query.get(test_user.id)
        assert u.mfa_enabled is False

def test_2fa_login_verification_success(client, test_user_with_2fa, app):
    # Step 1: Password
    client.post('/login', data={
        'identifier': test_user_with_2fa.username,
        'password': 'SecurePass123!@#'
    })

    # Step 2: 2FA TOTP
    secret = test_user_with_2fa.get_totp_secret()
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    response = client.post('/verify-2fa', data={'otp_code': valid_code}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Dashboard" in response.data

    with client.session_transaction() as sess:
        assert sess.get('2fa_verified') is True

def test_2fa_replay_rejection(client, test_user_with_2fa):
    secret = test_user_with_2fa.get_totp_secret()
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    # First verification should pass
    first_attempt = verify_totp(secret, valid_code, user_id=test_user_with_2fa.id)
    assert first_attempt is True

    # Immediate second verification of exact same code must be rejected (replay prevention)
    second_attempt = verify_totp(secret, valid_code, user_id=test_user_with_2fa.id)
    assert second_attempt is False

def test_2fa_verification_with_backup_code(client, test_user_with_2fa, app):
    client.post('/login', data={
        'identifier': test_user_with_2fa.username,
        'password': 'SecurePass123!@#'
    })

    response = client.post('/verify-2fa', data={'backup_code': 'RECO-VERY'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Dashboard" in response.data

    # Check that backup code was consumed
    with app.app_context():
        u = User.query.get(test_user_with_2fa.id)
        assert u.remaining_backup_codes_count() == 1
        # Reusing the consumed backup code must fail
        assert u.verify_and_consume_backup_code('RECO-VERY') is False
