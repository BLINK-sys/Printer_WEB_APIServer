from datetime import datetime, timezone

from ..extensions import db


class CloudProduct(db.Model):
    __tablename__ = 'cloud_products'

    id = db.Column(db.Integer, primary_key=True)
    database_id = db.Column(db.Integer, db.ForeignKey('product_databases.id', ondelete='CASCADE'), nullable=False)
    name_kz = db.Column(db.Text, nullable=False)
    name_full = db.Column(db.Text, nullable=False)
    barcode = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.Index('idx_cloud_products_db', 'database_id'),
        db.Index('idx_cloud_products_barcode', 'database_id', 'barcode'),
        db.Index('idx_cloud_products_name', 'database_id', 'name_kz'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'database_id': self.database_id,
            'name_kz': self.name_kz,
            'name_full': self.name_full,
            'barcode': self.barcode,
            'price': float(self.price),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
