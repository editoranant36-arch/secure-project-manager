from app.models.project import Project
from app.models.project_file import ProjectFile

def login_with_2fa(client, user):
    client.post('/login', data={'identifier': user.username, 'password': 'SecurePass123!@#'})
    with client.session_transaction() as sess:
        sess['2fa_verified'] = True
        sess['user_id'] = user.id

def test_unauthenticated_access_denied(client):
    res1 = client.get('/dashboard')
    assert res1.status_code == 302
    assert '/login' in res1.location

    res2 = client.get('/projects')
    assert res2.status_code == 302
    assert '/login' in res2.location

    res3 = client.get('/projects/upload')
    assert res3.status_code == 302
    assert '/login' in res3.location

def test_pending_2fa_access_denied(client, test_user_with_2fa):
    # Only supply password
    client.post('/login', data={
        'identifier': test_user_with_2fa.username,
        'password': 'SecurePass123!@#'
    })

    # Try directly navigating to dashboard
    res = client.get('/dashboard')
    assert res.status_code == 302
    assert '/verify-2fa' in res.location

    # Try directly navigating to projects
    res_proj = client.get('/projects')
    assert res_proj.status_code == 302
    assert '/verify-2fa' in res_proj.location

def test_cross_user_isolation(client, test_user_with_2fa, test_user_2, app):
    # Create Project owned by User B (test_user_2)
    with app.app_context():
        from app.extensions import db
        proj_b = Project(
            owner_id=test_user_2.id,
            project_name="User B Classified Project",
            version="1.0.0"
        )
        db.session.add(proj_b)
        db.session.commit()
        pid_b = proj_b.id

        file_b = ProjectFile(
            project_id=pid_b,
            original_filename="secret_key.txt",
            stored_filename="classified_dummy.txt",
            checksum="abc123",
            file_size=100
        )
        db.session.add(file_b)
        db.session.commit()
        fid_b = file_b.id

    # Now log in as User A (test_user_with_2fa)
    login_with_2fa(client, test_user_with_2fa)

    # 1. User A tries to view User B's project details
    view_res = client.get(f'/projects/{pid_b}')
    assert view_res.status_code == 404

    # 2. User A tries to edit User B's project
    edit_res = client.post(f'/projects/{pid_b}/edit', data={
        'project_name': 'Hacked Name'
    }, follow_redirects=True)
    assert b"unauthorized" in edit_res.data or b"Hacked Name" not in edit_res.data

    # 3. User A tries to delete User B's project
    del_res = client.post(f'/projects/{pid_b}/delete', follow_redirects=True)
    assert b"Make sure you own the project" in del_res.data

    # Verify project still exists in DB
    with app.app_context():
        assert Project.query.get(pid_b) is not None

    # 4. User A tries to download User B's file
    dl_res = client.get(f'/projects/{pid_b}/files/{fid_b}/download')
    assert dl_res.status_code == 404
