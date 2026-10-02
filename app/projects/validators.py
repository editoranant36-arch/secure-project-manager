import os
import mimetypes
from flask import current_app

def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return ext in allowed

def get_safe_mime_type(filename: str, provided_mime: str | None = None) -> str:
    """Determine MIME type safely from filename or provided header."""
    guessed_type, _ = mimetypes.guess_type(filename)
    if guessed_type:
        return guessed_type
    if provided_mime and '/' in provided_mime:
        return provided_mime
    return 'application/octet-stream'

def check_user_quota(user, additional_bytes: int = 0) -> tuple[bool, str]:
    """Check if user has sufficient quota for upload."""
    max_quota = current_app.config.get('MAX_STORAGE_PER_USER', 500 * 1024 * 1024)
    current_used = user.total_storage_used()
    if (current_used + additional_bytes) > max_quota:
        remaining_mb = max(0, (max_quota - current_used) / (1024 * 1024))
        return False, f"Storage quota exceeded. Available: {remaining_mb:.1f} MB"
    return True, ""
