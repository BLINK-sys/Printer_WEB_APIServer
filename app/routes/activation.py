from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..middleware.auth_required import jwt_required_custom
from ..models.activation_key import ActivationKey
from ..models.device import Device

activation_bp = Blueprint('activation', __name__)


@activation_bp.route('/status', methods=['GET'])
@jwt_required_custom
def status(user):
    """Check activation status for the current user's account."""
    now = datetime.now(timezone.utc)

    # Check for active activation key (account-based)
    active_key = ActivationKey.query.filter(
        ActivationKey.user_id == user.id,
        ActivationKey.status == 'activated',
        ActivationKey.expires_at > now,
    ).first()

    if active_key:
        days_remaining = (active_key.expires_at - now).days
        return jsonify({
            'status': 'active',
            'key_code': active_key.key_code,
            'email': active_key.activated_email,
            'activated_at': active_key.activated_at.isoformat() if active_key.activated_at else None,
            'expires_at': active_key.expires_at.isoformat(),
            'days_remaining': max(0, days_remaining),
        }), 200

    # Check for active trial on any device
    active_trial = Device.query.filter(
        Device.user_id == user.id,
        Device.trial_expires_at > now,
    ).first()

    if active_trial:
        days_remaining = (active_trial.trial_expires_at - now).days
        return jsonify({
            'status': 'trial',
            'expires_at': active_trial.trial_expires_at.isoformat(),
            'days_remaining': max(0, days_remaining),
        }), 200

    return jsonify({
        'status': 'expired',
        'days_remaining': 0,
    }), 200


@activation_bp.route('/activate', methods=['POST'])
@jwt_required_custom
def activate(user):
    """Activate a key for the current user's account."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    key_code = data.get('key_code', '').strip().upper()
    if not key_code:
        return jsonify({'error': 'Key code is required'}), 400

    # Find the key
    key = ActivationKey.query.filter_by(key_code=key_code).first()
    if not key:
        return jsonify({'error': 'Invalid activation key'}), 404

    if key.status == 'activated':
        return jsonify({'error': 'This key has already been activated'}), 409
    if key.status == 'revoked':
        return jsonify({'error': 'This key has been revoked'}), 409
    if key.status not in ('available', 'sold'):
        return jsonify({'error': 'This key cannot be activated'}), 400

    # Check if user already has an active key
    now = datetime.now(timezone.utc)
    existing_active = ActivationKey.query.filter(
        ActivationKey.user_id == user.id,
        ActivationKey.status == 'activated',
        ActivationKey.expires_at > now,
    ).first()

    # Activate the key (account-based)
    key.user_id = user.id
    key.activated_email = user.email
    key.activated_at = now
    key.expires_at = now + timedelta(days=key.duration_days)
    key.status = 'activated'
    db.session.commit()

    return jsonify({
        'message': 'Key activated successfully',
        'activation': {
            'status': 'active',
            'key_code': key.key_code,
            'email': key.activated_email,
            'activated_at': key.activated_at.isoformat(),
            'expires_at': key.expires_at.isoformat(),
            'days_remaining': key.duration_days,
        },
    }), 200


@activation_bp.route('/check-device', methods=['POST'])
def check_device():
    """Check if a device has already used its trial (no auth required)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    device_id = data.get('device_id', '')
    platform = data.get('platform', 'android')

    if not device_id:
        return jsonify({'error': 'device_id is required'}), 400

    existing = Device.query.filter_by(device_id=device_id, platform=platform).first()
    return jsonify({'trial_used': existing is not None}), 200
