import io
import hashlib
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.projects.storage import get_file_path

def login_with_2fa(client, user):
    client.post('/login', data={'identifier': user.username, 'password': 'SecurePass123!@#'})
    with client.session_transaction() as sess:
        sess['2fa_verified'] = True
        sess['user_id'] = user.id

def test_file_upload_allowed_type(client, test_user_with_2fa, app):
    login_with_2fa(client, test_user_with_2fa)

    with app.app_context():
        from app.extensions import db
        p = Project(owner_id=test_user_with_2fa.id, project_name='Upload Test', version='1.0.0')
        db.session.add(p)
        db.session.commit()
        pid = p.id

    content = b"print('Hello, secure sandbox world!')"
    data = {
        'files': (io.BytesIO(content), 'test_script.py')
    }

    res = client.post(f'/projects/{pid}/upload-file', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        file_rec = ProjectFile.query.filter_by(project_id=pid).first()
        assert file_rec is not None
        assert file_rec.original_filename == 'test_script.py'
        assert file_rec.file_size == len(content)
        assert file_rec.checksum == hashlib.sha256(content).hexdigest()

        # Check physical file exists in storage
        path = get_file_path(test_user_with_2fa.id, file_rec.stored_filename)
        assert path is not None
        assert path.exists()

def test_file_upload_prohibited_type_rejected(client, test_user_with_2fa, app):
    login_with_2fa(client, test_user_with_2fa)

    with app.app_context():
        from app.extensions import db
        p = Project(owner_id=test_user_with_2fa.id, project_name='Malicious Upload Test', version='1.0.0')
        db.session.add(p)
        db.session.commit()
        pid = p.id

    bad_content = b"#!/bin/bash\nrm -rf /"
    data = {
        'files': (io.BytesIO(bad_content), 'malware.sh')
    }

    res = client.post(f'/projects/{pid}/upload-file', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert b"File type not permitted" in res.data

    with app.app_context():
        assert ProjectFile.query.filter_by(project_id=pid).count() == 0

def test_path_traversal_sanitization(client, test_user_with_2fa, app):
    login_with_2fa(client, test_user_with_2fa)

    with app.app_context():
        from app.extensions import db
        p = Project(owner_id=test_user_with_2fa.id, project_name='Path Traversal Test', version='1.0.0')
        db.session.add(p)
        db.session.commit()
        pid = p.id

    evil_content = b"arbitrary content"
    # Attempt path traversal in filename
    data = {
        'files': (io.BytesIO(evil_content), '../../../../etc/passwd.txt')
    }

    res = client.post(f'/projects/{pid}/upload-file', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        file_rec = ProjectFile.query.filter_by(project_id=pid).first()
        assert file_rec is not None
        # Must be sanitized to safe basename (no ../)
        assert '..' not in file_rec.original_filename
        path = get_file_path(test_user_with_2fa.id, file_rec.stored_filename)
        assert path.exists()
        # Verify it stays strictly within the app's UPLOAD_FOLDER
        assert str(app.config['UPLOAD_FOLDER']) in str(path)
