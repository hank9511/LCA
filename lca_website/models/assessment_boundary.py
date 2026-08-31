from datetime import datetime
from extensions import db


class AssessmentBoundary(db.Model):

    __tablename__ = "assessment_boundary"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.String(8), db.ForeignKey("project.id"), nullable=False, index=True
    )

    lifecycle_model = db.Column(db.String(50), default="cradle_to_gate")

    lifecycle_stages = db.Column(db.Text)

    stages_config = db.Column(db.Text)

    boundary_description = db.Column(db.Text)

    functional_unit = db.Column(db.String(100))

    reference_flow = db.Column(db.String(100))

    cutoff_criteria = db.Column(db.Text)
    cutoff_threshold = db.Column(db.Float, default=1.0)

    process_flow_diagram = db.Column(db.String(500))

    geographical_boundary = db.Column(db.String(200))

    temporal_boundary = db.Column(db.String(200))

    technological_boundary = db.Column(db.Text)

    allocation_method = db.Column(db.String(50), default="mass")
    allocation_description = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<AssessmentBoundary for Project {self.project_id}>"

    def to_dict(self):

        return {
            "id": self.id,
            "project_id": self.project_id,
            "lifecycle_model": self.lifecycle_model,
            "functional_unit": self.functional_unit,
            "reference_flow": self.reference_flow,
            "cutoff_threshold": self.cutoff_threshold,
            "allocation_method": self.allocation_method,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
