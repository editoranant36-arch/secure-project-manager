import os
import uuid
import hashlib
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import current_app

def get_user_storage_path(user_id: int) -> Path:
    """Return the absolute path to the user's isolated storage directory."""
    base_upload_dir = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    user_dir = base_upload_dir / f"user_{user_id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Strictly verify that target_path does not traverse outside base_dir."""
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        return resolved_base in resolved_target.parents or resolved_base == resolved_target
    except Exception:
        return False

def save_uploaded_file(file_storage, user_id: int) -> tuple[str, str, int, str]:
    """
    Saves an uploaded file to the user's isolated storage directory.
    Returns: (stored_filename, safe_original_filename, file_size, sha256_checksum)
    """
    original_name = secure_filename(file_storage.filename or 'unnamed_file')
    if not original_name:
        original_name = 'unnamed_file'

    # Extract extension safely
    _, ext = os.path.splitext(original_name)
    ext = ext.lower()

    # Generate a randomized, non-guessable storage filename
    stored_name = f"{uuid.uuid4().hex}{ext}"
    user_dir = get_user_storage_path(user_id)
    target_path = user_dir / stored_name

    # Path traversal safety check
    if not is_safe_path(user_dir, target_path):
        raise ValueError("Invalid target storage path detected (path traversal attempt).")

    # Stream write while calculating SHA-256 and byte size
    sha256 = hashlib.sha256()
    size = 0
    try:
        file_storage.seek(0)
    except Exception:
        pass

    with open(target_path, 'wb') as f:
        while True:
            chunk = file_storage.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            sha256.update(chunk)
            size += len(chunk)

    return stored_name, original_name, size, sha256.hexdigest()

def get_file_path(user_id: int, stored_filename: str) -> Path | None:
    """Safely resolve file path for download/reading."""
    user_dir = get_user_storage_path(user_id)
    target_path = (user_dir / stored_filename).resolve()

    if not is_safe_path(user_dir, target_path) or not target_path.is_file():
        return None
    return target_path

def delete_stored_file(user_id: int, stored_filename: str) -> bool:
    """Delete a physical file from storage."""
    file_path = get_file_path(user_id, stored_filename)
    if file_path and file_path.exists():
        try:
            file_path.unlink()
            return True
        except Exception:
            return False
    return False
