import io
import zipfile
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    jsonify, send_file, abort
)
from flask_login import current_user
from app.auth.decorators import two_factor_required, api_two_factor_required
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.models.project_version import ProjectVersion
from app.projects.services import (
    create_project, update_project, delete_project,
    upload_file_to_project, delete_project_file_entry
)
from app.projects.storage import get_file_path
from app.extensions import db
from app.auth.services import log_audit_event

projects_bp = Blueprint('projects', __name__)

# ---------------- WEB INTERFACE ROUTES ----------------

@projects_bp.route('/projects')
@two_factor_required
def list_projects():
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    sort_by = request.args.get('sort', 'updated_at_desc')
    page = request.args.get('page', 1, type=int)
    per_page = 9

    query = Project.query.filter_by(owner_id=current_user.id)

    if search:
        query = query.filter(
            (Project.project_name.ilike(f'%{search}%')) |
            (Project.description.ilike(f'%{search}%'))
        )

    if category and category != 'All':
        query = query.filter_by(category=category)

    if sort_by == 'name_asc':
        query = query.order_by(Project.project_name.asc())
    elif sort_by == 'name_desc':
        query = query.order_by(Project.project_name.desc())
    elif sort_by == 'created_at_desc':
        query = query.order_by(Project.created_at.desc())
    elif sort_by == 'created_at_asc':
        query = query.order_by(Project.created_at.asc())
    else:
        query = query.order_by(Project.updated_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get distinct categories for filtering
    user_categories = [c[0] for c in db.session.query(Project.category).filter_by(owner_id=current_user.id).distinct().all()]

    return render_template(
        'projects.html',
        projects=pagination.items,
        pagination=pagination,
        search=search,
        category=category,
        sort_by=sort_by,
        user_categories=user_categories
    )


@projects_bp.route('/projects/upload', methods=['GET', 'POST'])
@two_factor_required
def upload_project():
    if request.method == 'POST':
        project_name = request.form.get('project_name', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General').strip()
        version = request.form.get('version', '1.0.0').strip()
        files = request.files.getlist('files')

        if not project_name:
            flash("Project name is required.", "danger")
            return render_template('upload.html')

        # Create project record
        project = create_project(
            user_id=current_user.id,
            project_name=project_name,
            description=description,
            category=category,
            version=version
        )

        # Upload files if attached
        uploaded_count = 0
        errors = []
        valid_files = [f for f in files if f and f.filename] if files else []
        for f in valid_files:
            file_obj, err = upload_file_to_project(project.id, current_user.id, f)
            if file_obj:
                uploaded_count += 1
            else:
                errors.append(f"{f.filename}: {err}")

        if errors:
            flash(f"Project created with warnings: {'; '.join(errors)}", "warning")
        elif uploaded_count > 0:
            flash(f"Project '{project_name}' created successfully with {uploaded_count} file(s).", "success")
        else:
            flash(f"Project '{project_name}' created successfully.", "success")

        return redirect(url_for('projects.project_details', project_id=project.id))

    return render_template('upload.html')


@projects_bp.route('/projects/<int:project_id>')
@two_factor_required
def project_details(project_id: int):
    project = Project.query.filter_by(id=project_id, owner_id=current_user.id).first_or_404()
    files = project.files.order_by(ProjectFile.uploaded_at.desc()).all()
    versions = project.versions.all()
    return render_template('project_details.html', project=project, files=files, versions=versions)


@projects_bp.route('/projects/<int:project_id>/edit', methods=['POST'])
@two_factor_required
def edit_project(project_id: int):
    project_name = request.form.get('project_name', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    version = request.form.get('version', '').strip()

    if not project_name:
        flash("Project name cannot be empty.", "danger")
        return redirect(url_for('projects.project_details', project_id=project_id))

    project = update_project(
        project_id=project_id,
        user_id=current_user.id,
        project_name=project_name,
        description=description,
        category=category,
        version=version
    )

    if not project:
        flash("Project not found or update unauthorized.", "danger")
        return redirect(url_for('projects.list_projects'))

    flash("Project metadata updated successfully.", "success")
    return redirect(url_for('projects.project_details', project_id=project_id))


@projects_bp.route('/projects/<int:project_id>/delete', methods=['POST'])
@two_factor_required
def delete_project_route(project_id: int):
    if delete_project(project_id, current_user.id):
        flash("Project and all associated files deleted successfully.", "success")
    else:
        flash("Failed to delete project. Make sure you own the project.", "danger")
    return redirect(url_for('projects.list_projects'))


@projects_bp.route('/projects/<int:project_id>/upload-file', methods=['POST'])
@two_factor_required
def upload_file_to_project_route(project_id: int):
    files = request.files.getlist('files')
    valid_files = [f for f in files if f and f.filename] if files else []
    if not valid_files:
        flash("No file was selected for upload.", "warning")
        return redirect(url_for('projects.project_details', project_id=project_id))

    successes = 0
    errors = []
    for f in valid_files:
        file_obj, err = upload_file_to_project(project_id, current_user.id, f)
        if file_obj:
            successes += 1
        else:
            errors.append(f"{f.filename}: {err}")

    if errors:
        flash(f"Uploaded {successes} file(s). Errors/Warnings: {'; '.join(errors)}", "warning")
    else:
        flash(f"Successfully uploaded {successes} file(s).", "success")

    return redirect(url_for('projects.project_details', project_id=project_id))


@projects_bp.route('/projects/<int:project_id>/files/<int:file_id>/download')
@two_factor_required
def download_project_file(project_id: int, file_id: int):
    file_record = ProjectFile.query.join(Project).filter(
        ProjectFile.id == file_id,
        ProjectFile.project_id == project_id,
        Project.owner_id == current_user.id
    ).first_or_404()

    path = get_file_path(current_user.id, file_record.stored_filename)
    if not path or not path.exists():
        log_audit_event('FILE_DOWNLOAD', 'FAILURE', user_id=current_user.id, details=f"File {file_record.original_filename} missing from disk")
        abort(404, description="File could not be found in secure storage.")

    log_audit_event('FILE_DOWNLOAD', 'SUCCESS', user_id=current_user.id, details=f"Downloaded '{file_record.original_filename}' from project {project_id}")

    return send_file(
        path,
        as_attachment=True,
        download_name=file_record.original_filename,
        mimetype=file_record.mime_type or 'application/octet-stream'
    )


@projects_bp.route('/projects/<int:project_id>/files/<int:file_id>/delete', methods=['POST'])
@two_factor_required
def delete_file_route(project_id: int, file_id: int):
    if delete_project_file_entry(file_id, current_user.id):
        flash("File deleted successfully.", "success")
    else:
        flash("Unable to delete file.", "danger")
    return redirect(url_for('projects.project_details', project_id=project_id))


@projects_bp.route('/projects/<int:project_id>/versions', methods=['POST'])
@two_factor_required
def add_version(project_id: int):
    project = Project.query.filter_by(id=project_id, owner_id=current_user.id).first_or_404()
    version_number = request.form.get('version_number', '').strip()
    change_description = request.form.get('change_description', '').strip()

    if not version_number:
        flash("Version number is required.", "danger")
        return redirect(url_for('projects.project_details', project_id=project_id))

    pv = ProjectVersion(
        project_id=project.id,
        version_number=version_number,
        change_description=change_description
    )
    project.version = version_number
    db.session.add(pv)
    db.session.commit()

    log_audit_event('PROJECT_VERSION', 'SUCCESS', user_id=current_user.id, details=f"Released v{version_number} for project {project.id}")
    flash(f"New version {version_number} recorded.", "success")
    return redirect(url_for('projects.project_details', project_id=project_id))


@projects_bp.route('/projects/<int:project_id>/download-archive')
@two_factor_required
def download_project_archive(project_id: int):
    project = Project.query.filter_by(id=project_id, owner_id=current_user.id).first_or_404()
    files = project.files.all()

    if not files:
        flash("No files in project to archive.", "warning")
        return redirect(url_for('projects.project_details', project_id=project_id))

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            path = get_file_path(current_user.id, f.stored_filename)
            if path and path.exists():
                zf.write(path, arcname=f.original_filename)

    memory_file.seek(0)
    safe_name = f"{project.project_name.replace(' ', '_')}_v{project.version}.zip"
    log_audit_event('PROJECT_ARCHIVE_DOWNLOAD', 'SUCCESS', user_id=current_user.id, details=f"Downloaded archive for project {project.id}")

    return send_file(
        memory_file,
        as_attachment=True,
        download_name=safe_name,
        mimetype='application/zip'
    )


# ---------------- RESTFUL API ENDPOINTS ----------------

@projects_bp.route('/api/projects', methods=['GET'])
@api_two_factor_required
def api_get_projects():
    projects = Project.query.filter_by(owner_id=current_user.id).order_by(Project.updated_at.desc()).all()
    return jsonify({'success': True, 'projects': [p.to_dict() for p in projects]}), 200


@projects_bp.route('/api/projects', methods=['POST'])
@api_two_factor_required
def api_create_project():
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name', '').strip()
    description = data.get('description', '').strip()
    category = data.get('category', 'General').strip()
    version = data.get('version', '1.0.0').strip()

    if not project_name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'project_name is required'}), 400

    project = create_project(
        user_id=current_user.id,
        project_name=project_name,
        description=description,
        category=category,
        version=version
    )
    return jsonify({'success': True, 'project': project.to_dict()}), 201


@projects_bp.route('/api/projects/<int:project_id>', methods=['GET'])
@api_two_factor_required
def api_get_project(project_id: int):
    project = Project.query.filter_by(id=project_id, owner_id=current_user.id).first()
    if not project:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Project not found'}), 404

    files = [f.to_dict() for f in project.files.all()]
    versions = [v.to_dict() for v in project.versions.all()]
    data = project.to_dict()
    data['files'] = files
    data['versions'] = versions
    return jsonify({'success': True, 'project': data}), 200


@projects_bp.route('/api/projects/<int:project_id>', methods=['PATCH'])
@api_two_factor_required
def api_update_project(project_id: int):
    data = request.get_json(silent=True) or {}
    project = update_project(
        project_id=project_id,
        user_id=current_user.id,
        project_name=data.get('project_name'),
        description=data.get('description'),
        category=data.get('category'),
        version=data.get('version')
    )
    if not project:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Project not found or forbidden'}), 404
    return jsonify({'success': True, 'project': project.to_dict()}), 200


@projects_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
@api_two_factor_required
def api_delete_project(project_id: int):
    if delete_project(project_id, current_user.id):
        return jsonify({'success': True, 'message': 'Project deleted'}), 200
    return jsonify({'error': 'NOT_FOUND', 'message': 'Project not found or forbidden'}), 404


@projects_bp.route('/api/projects/<int:project_id>/files', methods=['GET'])
@api_two_factor_required
def api_get_project_files(project_id: int):
    project = Project.query.filter_by(id=project_id, owner_id=current_user.id).first()
    if not project:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Project not found'}), 404
    return jsonify({'success': True, 'files': [f.to_dict() for f in project.files.all()]}), 200


@projects_bp.route('/api/projects/<int:project_id>/files', methods=['POST'])
@api_two_factor_required
def api_upload_project_file(project_id: int):
    if 'file' not in request.files:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'No file provided in request'}), 400

    f = request.files['file']
    file_obj, err = upload_file_to_project(project_id, current_user.id, f)
    if not file_obj:
        return jsonify({'error': 'UPLOAD_FAILED', 'message': err}), 400

    return jsonify({'success': True, 'file': file_obj.to_dict()}), 201


@projects_bp.route('/api/projects/<int:project_id>/files/<int:file_id>/download', methods=['GET'])
@api_two_factor_required
def api_download_file(project_id: int, file_id: int):
    file_record = ProjectFile.query.join(Project).filter(
        ProjectFile.id == file_id,
        ProjectFile.project_id == project_id,
        Project.owner_id == current_user.id
    ).first()

    if not file_record:
        return jsonify({'error': 'NOT_FOUND', 'message': 'File not found'}), 404

    path = get_file_path(current_user.id, file_record.stored_filename)
    if not path or not path.exists():
        return jsonify({'error': 'STORAGE_ERROR', 'message': 'Physical file missing from storage'}), 500

    return send_file(path, as_attachment=True, download_name=file_record.original_filename)


@projects_bp.route('/api/projects/<int:project_id>/versions', methods=['POST'])
@api_two_factor_required
def api_create_version(project_id: int):
    project = Project.query.filter_by(id=project_id, owner_id=current_user.id).first()
    if not project:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Project not found'}), 404

    data = request.get_json(silent=True) or {}
    version_number = data.get('version_number', '').strip()
    change_description = data.get('change_description', '').strip()

    if not version_number:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'version_number is required'}), 400

    pv = ProjectVersion(
        project_id=project.id,
        version_number=version_number,
        change_description=change_description
    )
    project.version = version_number
    db.session.add(pv)
    db.session.commit()

    return jsonify({'success': True, 'version': pv.to_dict()}), 201
