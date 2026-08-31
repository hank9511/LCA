from datetime import datetime
import random
import string
from extensions import db


def generate_short_id():

    chars = string.ascii_uppercase.replace("O", "").replace(
        "I", ""
    ) + string.digits.replace("0", "").replace("1", "")
    return "".join(random.choice(chars) for _ in range(8))


class Project(db.Model):

    __tablename__ = "project"

    id = db.Column(db.String(8), primary_key=True, default=generate_short_id)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="active", index=True)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )

    lca_data = db.relationship(
        "LCAData", backref="project", lazy="dynamic", cascade="all, delete-orphan"
    )
    excel_files = db.relationship(
        "ExcelFile", backref="project", lazy="dynamic", cascade="all, delete-orphan"
    )
    assessment_boundary = db.relationship(
        "AssessmentBoundary",
        backref="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    report_info = db.relationship(
        "ProjectReportInfo",
        backref="project",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Project {self.name}>"

    def to_dict(self):

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "user_id": self.user_id,
        }

    @property
    def is_active(self):

        return self.status == "active"

    @property
    def file_count(self):

        return self.excel_files.count()
