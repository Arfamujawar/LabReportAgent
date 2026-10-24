from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    pw = db.Column(db.String(256), nullable=False)
    created = db.Column(db.DateTime, default=datetime.utcnow)
    reports = db.relationship("Report", backref="owner", cascade="all,delete-orphan")

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    stored = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(16), default="Uploaded")

    # Human review and verification
    review_status = db.Column(
        db.String(24),
        nullable=False,
        default="Pending Review",
        server_default="Pending Review"
    )
    review_notes = db.Column(
        db.Text,
        nullable=False,
        default="",
        server_default=""
    )
    reviewed_at = db.Column(db.DateTime, nullable=True)

    warning = db.Column(db.Text, default="")
    created = db.Column(db.DateTime, default=datetime.utcnow)
    results = db.relationship("Result", backref="report", cascade="all,delete-orphan")
class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer, db.ForeignKey("report.id"), nullable=False, index=True
    )
    name = db.Column(db.String(80), nullable=False)
    value = db.Column(db.Float, nullable=True)
    text_value = db.Column(db.String(120), nullable=True)
    unit = db.Column(db.String(24), default="")
    low = db.Column(db.Float, nullable=True)
    high = db.Column(db.Float, nullable=True)
    flag = db.Column(db.String(8), default="")
