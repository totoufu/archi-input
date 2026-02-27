from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


class Work(db.Model):
    __tablename__ = 'works'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), default='')
    url = db.Column(db.String(2000), default='')
    notes = db.Column(db.Text, default='')
    is_reviewed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # --- AI-extracted fields ---
    architect = db.Column(db.String(300), default='')
    year = db.Column(db.Integer, nullable=True)
    country = db.Column(db.String(100), default='')
    city = db.Column(db.String(100), default='')
    usage = db.Column(db.String(100), default='')
    structure = db.Column(db.String(100), default='')
    ai_description = db.Column(db.Text, default='')
    thumbnail_url = db.Column(db.String(2000), default='')
    is_analyzed = db.Column(db.Boolean, default=False)

    # --- Image & visual analysis ---
    image_path = db.Column(db.String(500), default='')   # local file path
    visual_analysis = db.Column(db.Text, default='')     # Gemini visual analysis

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'notes': self.notes,
            'is_reviewed': self.is_reviewed,
            'architect': self.architect,
            'year': self.year,
            'country': self.country,
            'city': self.city,
            'usage': self.usage,
            'structure': self.structure,
            'ai_description': self.ai_description,
            'thumbnail_url': self.thumbnail_url,
            'is_analyzed': self.is_analyzed,
            'image_path': self.image_path,
            'visual_analysis': self.visual_analysis,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
