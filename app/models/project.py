from datetime import datetime, timezone
from app.extensions import db

class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    project_name = db.Column(db.String(150), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default='General', nullable=False, index=True)
    version = db.Column(db.String(30), default='1.0.0', nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    files = db.relationship('ProjectFile', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    versions = db.relationship('ProjectVersion', backref='project', lazy='dynamic', cascade='all, delete-orphan', order_by='ProjectVersion.uploaded_at.desc()')

    def total_size(self) -> int:
        return sum(f.file_size for f in self.files.all() if f.file_size)

    def file_count(self) -> int:
        return self.files.count()

    def to_dict(self):
        return {
            'id': self.id,
            'owner_id': self.owner_id,
            'project_name': self.project_name,
            'description': self.description,
            'category': self.category,
            'version': self.version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'total_size': self.total_size(),
            'file_count': self.file_count()
        }

    def __repr__(self):
        return f'<Project {self.project_name} (User {self.owner_id})>'
