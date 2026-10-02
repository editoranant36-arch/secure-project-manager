import io
import base64
import secrets
import string
from datetime import datetime, timezone
import pyotp
import qrcode
from qrcode.image.pil import PilImage
from flask import current_app

# In-memory replay cache: (user_id, time_step) -> timestamp
# Prevents replay of the exact same OTP code in the same 30s window
_USED_OTP_TIMESTEPS = {}

def generate_totp_secret() -> str:
    """Generate a standard base32 TOTP secret."""
    return pyotp.random_base32()

def get_totp_uri(secret: str, username: str, issuer: str | None = None) -> str:
    """Build otpauth:// URI compatible with Google Authenticator and Microsoft Authenticator."""
    if not issuer:
        issuer = current_app.config.get('TOTP_ISSUER_NAME', 'SecureProjectManager')
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)

def generate_qr_code_base64(provisioning_uri: str) -> str:
    """Generate a PNG QR code encoded as a data URI."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#00f2fe", back_color="#0a0f1d")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

def verify_totp(secret: str, code: str, user_id: int | None = None, valid_window: int = 1) -> bool:
    """
    Verify TOTP code using PyOTP with a +- 1 window (30s before/after).
    Enforces replay prevention to reject reusing an OTP code within the same interval.
    """
    if not secret or not code:
        return False
    
    clean_code = str(code).strip().replace(" ", "").replace("-", "")
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False

    totp = pyotp.TOTP(secret)
    time_step = totp.timecode(datetime.now())
    
    # Check if this user already used this time-step recently
    if user_id is not None:
        last_step = _USED_OTP_TIMESTEPS.get(user_id)
        if last_step is not None and abs(last_step - time_step) <= valid_window:
            # Check if this exact code matches the currently active timecode
            if totp.verify(clean_code, valid_window=valid_window):
                # If they already consumed this specific window step, reject replay
                if _USED_OTP_TIMESTEPS.get((user_id, clean_code)):
                    return False

    # Perform verification
    is_valid = totp.verify(clean_code, valid_window=valid_window)
    if is_valid and user_id is not None:
        _USED_OTP_TIMESTEPS[user_id] = time_step
        _USED_OTP_TIMESTEPS[(user_id, clean_code)] = True
        # Periodic cleanup of dict if large
        if len(_USED_OTP_TIMESTEPS) > 10000:
            _USED_OTP_TIMESTEPS.clear()

    return is_valid

def generate_backup_codes(count: int = 8, length: int = 10) -> list[str]:
    """Generate human-readable, single-use backup recovery codes formatted as XXXX-XXXX."""
    chars = string.ascii_uppercase + string.digits
    codes = []
    for _ in range(count):
        raw = ''.join(secrets.choice(chars) for _ in range(length))
        formatted = f"{raw[:4]}-{raw[4:8]}"
        codes.append(formatted)
    return codes
