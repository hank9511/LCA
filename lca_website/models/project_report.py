from datetime import datetime
from extensions import db


class ProjectReportInfo(db.Model):

    __tablename__ = "project_report_info"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.String(8),
        db.ForeignKey("project.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    product_name = db.Column(db.Text)
    product_model = db.Column(db.Text)
    producer_name = db.Column(db.Text)
    report_no = db.Column(db.Text)
    address = db.Column(db.Text)
    legal_representative = db.Column(db.Text)
    contact_person = db.Column(db.Text)
    contact_phone = db.Column(db.Text)
    contact_email = db.Column(db.Text)

    product_function = db.Column(db.Text)
    standard_used = db.Column(db.Text, default="ecoinvent - EF v3.1")

    quantitative_purpose = db.Column(db.Text)
    functional_unit = db.Column(db.Text)
    system_boundary_description = db.Column(db.Text)
    system_boundary_stages = db.Column(db.Text)
    cutoff_criteria = db.Column(db.Text)
    time_scale = db.Column(db.Text)

    primary_data_source = db.Column(db.Text)
    secondary_data_source = db.Column(db.Text)

    allocation_basis = db.Column(db.Text)
    allocation_procedure = db.Column(db.Text)
    specific_allocations = db.Column(db.Text)

    data_quality_notes = db.Column(db.Text)

    impact_type_description = db.Column(
        db.Text, default="100-year global warming potential (GWP) given by IPCC"
    )

    assumptions_limitations = db.Column(db.Text)
    improvement_suggestions = db.Column(db.Text)

    enable_ai_suggestions = db.Column(db.Boolean, default=True)
    report_language = db.Column(db.String(10), default="en")

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<ProjectReportInfo for Project {self.project_id}>"

    def to_dict(self):

        return {
            "id": self.id,
            "project_id": self.project_id,
            "product_name": self.product_name,
            "product_model": self.product_model,
            "producer_name": self.producer_name,
            "standard_used": self.standard_used,
            "functional_unit": self.functional_unit,
            "report_language": self.report_language,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
