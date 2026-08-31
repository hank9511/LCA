from datetime import datetime
from extensions import db


class ExcelFile(db.Model):

    __tablename__ = "excel_file"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.String(8), db.ForeignKey("project.id"), nullable=False, index=True
    )
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.now, index=True)

    llm_analysis = db.Column(db.Text)
    llm_suggestions = db.Column(db.Text)
    analysis_time = db.Column(db.DateTime)

    metadata_json = db.Column(db.JSON)

    is_deleted = db.Column(db.Boolean, default=False, index=True)
    deleted_time = db.Column(db.DateTime)

    lca_results = db.relationship(
        "LCAResult", backref="excel_file", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ExcelFile {self.original_filename}>"

    def to_dict(self):

        return {
            "id": self.id,
            "project_id": self.project_id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "upload_time": self.upload_time.isoformat() if self.upload_time else None,
            "is_deleted": self.is_deleted,
            "has_analysis": bool(self.llm_analysis),
        }

    @property
    def size_mb(self):

        return round(self.file_size / (1024 * 1024), 2) if self.file_size else 0
