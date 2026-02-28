from datetime import datetime, timezone

from ..extensions import db


class ActivationKey(db.Model):
    __tablename__ = 'activation_keys'

    id = db.Column(db.Integer, primary_key=True)
    key_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    duration_days = db.Column(db.Integer, default=365, nullable=False)
    status = db.Column(db.String(20), default='available', nullable=False)
    # available / sold / activated / expired / revoked

    # Filled on activation
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    activated_email = db.Column(db.String(255), nullable=True)
    activated_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    # Sales tracking
    sold_to_name = db.Column(db.String(255), nullable=True)
    sold_to_email = db.Column(db.String(255), nullable=True)
    sold_at = db.Column(db.DateTime, nullable=True)
    sold_price = db.Column(db.Numeric(10, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Admin who created the key
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', foreign_keys=[created_by], backref='created_keys')

    def to_dict(self):
        return {
            'id': self.id,
            'key_code': self.key_code,
            'duration_days': self.duration_days,
            'status': self.status,
            'user_id': self.user_id,
            'activated_email': self.activated_email,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'sold_to_name': self.sold_to_name,
            'sold_to_email': self.sold_to_email,
            'sold_at': self.sold_at.isoformat() if self.sold_at else None,
            'sold_price': float(self.sold_price) if self.sold_price else None,
            'notes': self.notes,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
