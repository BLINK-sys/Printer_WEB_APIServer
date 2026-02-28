from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..middleware.auth_required import jwt_required_custom
from ..models.activation_key import ActivationKey
from ..models.device import Device
from ..models.user import User
from ..utils.validators import validate_email, validate_password

auth_bp = Blueprint('auth', __name__)


def _get_activation_status(user):
    """Get activation status for a user (account-based, not device-based)."""
    if user.is_admin:
        return {'status': 'active', 'days_remaining': 999}

    now = datetime.now(timezone.utc)

    # Check for active activation key
    active_key = ActivationKey.query.filter(
        ActivationKey.user_id == user.id,
        ActivationKey.status == 'activated',
        ActivationKey.expires_at > now,
    ).first()

    if active_key:
        days_remaining = (active_key.expires_at - now).days
        return {
            'status': 'active',
            'key_code': active_key.key_code,
            'email': active_key.activated_email,
            'activated_at': active_key.activated_at.isoformat() if active_key.activated_at else None,
            'expires_at': active_key.expires_at.isoformat(),
            'days_remaining': max(0, days_remaining),
        }

    # Check for active trial on any device of this user
    active_trial = Device.query.filter(
        Device.user_id == user.id,
        Device.trial_expires_at > now,
    ).first()

    if active_trial:
        days_remaining = (active_trial.trial_expires_at - now).days
        hours_remaining = (active_trial.trial_expires_at - now).seconds // 3600
        return {
            'status': 'trial',
            'expires_at': active_trial.trial_expires_at.isoformat(),
            'days_remaining': max(0, days_remaining),
            'hours_remaining': hours_remaining,
        }

    return {'status': 'expired', 'days_remaining': 0}


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    device_id = data.get('device_id', '')
    platform = data.get('platform', 'android')

    if not email or not password or not device_id:
        return jsonify({'error': 'Email, password, and device_id are required'}), 400
    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400
    if not validate_password(password):
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if platform not in ('android', 'web'):
        return jsonify({'error': 'Platform must be android or web'}), 400

    # Check email uniqueness
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    # Check device trial
    existing_device = Device.query.filter_by(device_id=device_id, platform=platform).first()
    if existing_device:
        return jsonify({
            'error': 'This device has already been used for a trial period',
            'trial_used': True,
        }), 409

    # Create user
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.flush()

    # Create device with trial
    now = datetime.now(timezone.utc)
    from flask import current_app
    trial_days = current_app.config.get('TRIAL_DURATION_DAYS', 3)

    device = Device(
        user_id=user.id,
        device_id=device_id,
        platform=platform,
        trial_started_at=now,
        trial_expires_at=now + timedelta(days=trial_days),
    )
    db.session.add(device)
    db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify({
        'user': user.to_dict(),
        'access_token': access_token,
        'refresh_token': refresh_token,
        'activation': _get_activation_status(user),
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    device_id = data.get('device_id', '')
    platform = data.get('platform', 'android')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid email or password'}), 401

    if not user.is_active:
        return jsonify({'error': 'Account disabled'}), 403

    # Register device if new (but don't create a trial — trial is only on registration)
    if device_id and platform:
        existing_device = Device.query.filter_by(user_id=user.id, device_id=device_id, platform=platform).first()
        if not existing_device:
            # Just track the device, no new trial
            device = Device(
                user_id=user.id,
                device_id=device_id,
                platform=platform,
                trial_started_at=datetime.now(timezone.utc),
                trial_expires_at=datetime.now(timezone.utc),  # Already expired — no trial on login
            )
            db.session.add(device)
            db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify({
        'user': user.to_dict(),
        'access_token': access_token,
        'refresh_token': refresh_token,
        'activation': _get_activation_status(user),
    }), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required_custom
def me(user):
    return jsonify({
        'user': user.to_dict(),
        'activation': _get_activation_status(user),
    }), 200


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not user.is_active:
        return jsonify({'error': 'Account disabled'}), 403

    access_token = create_access_token(identity=user_id)
    return jsonify({'access_token': access_token}), 200
