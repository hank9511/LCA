from datetime import datetime
from extensions import db


class LCAData(db.Model):

    __tablename__ = "lca_data"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.String(8), db.ForeignKey("project.id"), nullable=False, index=True
    )
    data_type = db.Column(db.String(50), nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    def __repr__(self):
        return f"<LCAData {self.data_type}: {self.value} {self.unit}>"

    def to_dict(self):

        return {
            "id": self.id,
            "project_id": self.project_id,
            "data_type": self.data_type,
            "value": self.value,
            "unit": self.unit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
