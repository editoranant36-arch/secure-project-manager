from app.extensions import db
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.models.project_version import ProjectVersion
from app.models.user import User
from app.projects.storage import save_uploaded_file, delete_stored_file
from app.projects.validators import is_allowed_file, get_safe_mime_type, check_user_quota
from app.auth.services import log_audit_event

def create_project(user_id: int, project_name: str, description: str = '', category: str = 'General', version: str = '1.0.0') -> Project:
    project = Project(
        owner_id=user_id,
        project_name=project_name.strip(),
        description=description.strip() if description else '',
        category=category.strip() if category else 'General',
        version=version.strip() if version else '1.0.0'
    )
    db.session.add(project)
    db.session.commit()

    # Create initial version entry
    initial_version = ProjectVersion(
        project_id=project.id,
        version_number=project.version,
        change_description='Initial project release'
    )
    db.session.add(initial_version)
    db.session.commit()

    log_audit_event('PROJECT_CREATE', 'SUCCESS', user_id=user_id, details=f"Created project '{project_name}' (ID: {project.id})")
    return project

def update_project(project_id: int, user_id: int, project_name: str | None = None, description: str | None = None, category: str | None = None, version: str | None = None) -> Project | None:
    project = Project.query.filter_by(id=project_id, owner_id=user_id).first()
    if not project:
        return None

    if project_name is not None and project_name.strip():
        project.project_name = project_name.strip()
    if description is not None:
        project.description = description.strip()
    if category is not None and category.strip():
        project.category = category.strip()
    if version is not None and version.strip():
        if version.strip() != project.version:
            # Record version upgrade
            v = ProjectVersion(
                project_id=project.id,
                version_number=version.strip(),
                change_description='Version updated via project settings'
            )
            db.session.add(v)
        project.version = version.strip()

    db.session.commit()
    log_audit_event('PROJECT_UPDATE', 'SUCCESS', user_id=user_id, details=f"Updated project {project.id}")
    return project

def delete_project(project_id: int, user_id: int) -> bool:
    project = Project.query.filter_by(id=project_id, owner_id=user_id).first()
    if not project:
        return False

    # Delete physical files
    files = project.files.all()
    for file in files:
        delete_stored_file(user_id, file.stored_filename)

    name = project.project_name
    db.session.delete(project)
    db.session.commit()
    log_audit_event('PROJECT_DELETE', 'SUCCESS', user_id=user_id, details=f"Deleted project '{name}' and associated files")
    return True

def upload_file_to_project(project_id: int, user_id: int, file_storage) -> tuple[ProjectFile | None, str]:
    project = Project.query.filter_by(id=project_id, owner_id=user_id).first()
    if not project:
        return None, "Project not found or access denied."

    if not file_storage or not file_storage.filename:
        return None, "No file selected."

    if not is_allowed_file(file_storage.filename):
        return None, f"File type not permitted. Permitted types: {', '.join(sorted(file_storage._app_config if hasattr(file_storage, '_app_config') else ['zip', 'py', 'js', 'html', 'css', 'pdf', 'png', 'jpg']))}"

    user = User.query.get(user_id)
    # Check quota before saving
    has_quota, quota_err = check_user_quota(user)
    if not has_quota:
        return None, quota_err

    try:
        stored_name, safe_orig, size, checksum = save_uploaded_file(file_storage, user_id)
    except Exception as e:
        return None, f"Error saving file: {str(e)}"

    # Check quota with actual size
    if not check_user_quota(user, size)[0]:
        delete_stored_file(user_id, stored_name)
        return None, "File exceeds available storage quota."

    mime = get_safe_mime_type(safe_orig, file_storage.mimetype)

    # Check if a file with this original name already exists in this project
    existing = ProjectFile.query.filter_by(project_id=project.id, original_filename=safe_orig).first()
    if existing:
        # Replace existing file record & physical file
        delete_stored_file(user_id, existing.stored_filename)
        existing.stored_filename = stored_name
        existing.file_size = size
        existing.checksum = checksum
        existing.mime_type = mime
        db.session.commit()
        log_audit_event('FILE_UPDATE', 'SUCCESS', user_id=user_id, details=f"Updated file '{safe_orig}' in project {project.id}")
        return existing, ""

    project_file = ProjectFile(
        project_id=project.id,
        original_filename=safe_orig,
        stored_filename=stored_name,
        mime_type=mime,
        file_size=size,
        checksum=checksum
    )
    db.session.add(project_file)
    db.session.commit()

    log_audit_event('FILE_UPLOAD', 'SUCCESS', user_id=user_id, details=f"Uploaded file '{safe_orig}' ({size} bytes) to project {project.id}")
    return project_file, ""

def delete_project_file_entry(file_id: int, user_id: int) -> bool:
    file = ProjectFile.query.join(Project).filter(
        ProjectFile.id == file_id,
        Project.owner_id == user_id
    ).first()

    if not file:
        return False

    delete_stored_file(user_id, file.stored_filename)
    filename = file.original_filename
    project_id = file.project_id
    db.session.delete(file)
    db.session.commit()
    log_audit_event('FILE_DELETE', 'SUCCESS', user_id=user_id, details=f"Deleted file '{filename}' from project {project_id}")
    return True
