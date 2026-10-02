from datetime import datetime, timezone
from app.extensions import db

class ProjectVersion(db.Model):
    __tablename__ = 'project_versions'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    version_number = db.Column(db.String(30), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    change_description = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'version_number': self.version_number,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'change_description': self.change_description
        }

    def __repr__(self):
        return f'<ProjectVersion v{self.version_number} (Project {self.project_id})>'
