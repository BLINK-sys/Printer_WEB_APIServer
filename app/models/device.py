from datetime import datetime, timezone

from ..extensions import db


class Device(db.Model):
    __tablename__ = 'devices'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    device_id = db.Column(db.String(512), nullable=False)
    platform = db.Column(db.String(50), nullable=False)  # 'android' or 'web'
    trial_started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    trial_expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('device_id', 'platform', name='uq_device_platform'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'device_id': self.device_id,
            'platform': self.platform,
            'trial_started_at': self.trial_started_at.isoformat() if self.trial_started_at else None,
            'trial_expires_at': self.trial_expires_at.isoformat() if self.trial_expires_at else None,
        }
