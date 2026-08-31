from datetime import datetime
from extensions import db


class LCAResult(db.Model):

    __tablename__ = "lca_result"

    id = db.Column(db.Integer, primary_key=True)
    excel_file_id = db.Column(
        db.Integer, db.ForeignKey("excel_file.id"), nullable=False, index=True
    )

    analysis_status = db.Column(db.String(20), default="pending", index=True)
    start_time = db.Column(db.DateTime, default=datetime.now, index=True)
    end_time = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Float)

    flows_count = db.Column(db.Integer)
    processes_count = db.Column(db.Integer)
    product_systems_count = db.Column(db.Integer)

    openLCA_connected = db.Column(db.Boolean, default=False)

    error_message = db.Column(db.Text)

    analysis_details = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f"<LCAResult {self.id} - {self.analysis_status}>"

    def to_dict(self):

        return {
            "id": self.id,
            "excel_file_id": self.excel_file_id,
            "analysis_status": self.analysis_status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "flows_count": self.flows_count,
            "processes_count": self.processes_count,
            "product_systems_count": self.product_systems_count,
            "openLCA_connected": self.openLCA_connected,
            "has_error": bool(self.error_message),
        }

    @property
    def is_complete(self):

        return self.analysis_status == "completed"

    @property
    def is_failed(self):

        return self.analysis_status == "failed"

    @property
    def is_running(self):

        return self.analysis_status == "running"
