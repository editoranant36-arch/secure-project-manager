import io
from app.models.project import Project
from app.models.project_version import ProjectVersion

def login_with_2fa(client, user):
    client.post('/login', data={'identifier': user.username, 'password': 'SecurePass123!@#'})
    with client.session_transaction() as sess:
        sess['2fa_verified'] = True
        sess['user_id'] = user.id

def test_create_and_list_projects(client, test_user_with_2fa, app):
    login_with_2fa(client, test_user_with_2fa)

    response = client.post('/projects/upload', data={
        'project_name': 'Zero Trust Network',
        'category': 'Cyber Security',
        'version': '1.0.0',
        'description': 'Network micro-segmentation suite'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Zero Trust Network" in response.data

    with app.app_context():
        p = Project.query.filter_by(project_name='Zero Trust Network').first()
        assert p is not None
        assert p.owner_id == test_user_with_2fa.id
        assert p.category == 'Cyber Security'

def test_update_project(client, test_user_with_2fa, app):
    login_with_2fa(client, test_user_with_2fa)

    # Create project
    with app.app_context():
        p = Project(owner_id=test_user_with_2fa.id, project_name='Old Name', version='1.0.0')
        from app.extensions import db
        db.session.add(p)
        db.session.commit()
        pid = p.id

    response = client.post(f'/projects/{pid}/edit', data={
        'project_name': 'New Fortified Name',
        'category': 'Cloud Infrastructure',
        'version': '1.1.0',
        'description': 'Updated description'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        p = Project.query.get(pid)
        assert p.project_name == 'New Fortified Name'
        assert p.version == '1.1.0'

def test_delete_project(client, test_user_with_2fa, app):
    login_with_2fa(client, test_user_with_2fa)

    with app.app_context():
        from app.extensions import db
        p = Project(owner_id=test_user_with_2fa.id, project_name='Project to Delete', version='1.0.0')
        db.session.add(p)
        db.session.commit()
        pid = p.id

    del_res = client.post(f'/projects/{pid}/delete', follow_redirects=True)
    assert del_res.status_code == 200

    with app.app_context():
        assert Project.query.get(pid) is None

def test_add_project_version(client, test_user_with_2fa, app):
    login_with_2fa(client, test_user_with_2fa)

    with app.app_context():
        from app.extensions import db
        p = Project(owner_id=test_user_with_2fa.id, project_name='Versioned Project', version='1.0.0')
        db.session.add(p)
        db.session.commit()
        pid = p.id

    res = client.post(f'/projects/{pid}/versions', data={
        'version_number': '2.0.0',
        'change_description': 'Refactored auth module'
    }, follow_redirects=True)

    assert res.status_code == 200
    with app.app_context():
        p = Project.query.get(pid)
        assert p.version == '2.0.0'
        versions = p.versions.all()
        assert any(v.version_number == '2.0.0' for v in versions)
