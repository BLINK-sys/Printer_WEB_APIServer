from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from werkzeug.security import generate_password_hash

from ..extensions import db
from ..middleware.auth_required import admin_required
from ..models.activation_key import ActivationKey
from ..models.device import Device
from ..models.product_database import ProductDatabase
from ..models.user import User
from ..utils.key_generator import generate_activation_key

admin_bp = Blueprint('admin', __name__)


# --- Stats ---

@admin_bp.route('/stats', methods=['GET'])
@admin_required
def stats(user):
    now = datetime.utcnow()

    total_users = User.query.count()
    active_trials = Device.query.filter(Device.trial_expires_at > now).distinct(Device.user_id).count()
    active_keys = ActivationKey.query.filter(
        ActivationKey.status == 'activated',
        ActivationKey.expires_at > now,
    ).count()
    admin_count = User.query.filter_by(is_admin=True).count()
    expired_users = total_users - active_trials - active_keys - admin_count
    total_keys = ActivationKey.query.count()
    available_keys = ActivationKey.query.filter_by(status='available').count()
    sold_keys = ActivationKey.query.filter_by(status='sold').count()

    revenue = db.session.query(
        db.func.coalesce(db.func.sum(ActivationKey.sold_price), 0)
    ).filter(ActivationKey.sold_price.isnot(None)).scalar()

    recent_users = User.query.filter(User.id != 1).order_by(User.created_at.desc()).limit(10).all()

    # Compute activation status for each recent user
    recent_users_data = []
    for u in recent_users:
        u_dict = u.to_dict()
        if u.is_admin:
            u_dict['activation_status'] = 'active'
        else:
            active_key = ActivationKey.query.filter(
                ActivationKey.user_id == u.id,
                ActivationKey.status == 'activated',
                ActivationKey.expires_at > now,
            ).first()
            if active_key:
                u_dict['activation_status'] = 'active'
            else:
                trial = Device.query.filter(
                    Device.user_id == u.id,
                    Device.trial_expires_at > now,
                ).first()
                if trial:
                    u_dict['activation_status'] = 'trial'
                else:
                    u_dict['activation_status'] = 'expired'
        recent_users_data.append(u_dict)

    return jsonify({
        'total_users': total_users,
        'active_trials': active_trials,
        'active_keys': active_keys,
        'expired_users': max(0, expired_users),
        'total_keys': total_keys,
        'available_keys': available_keys,
        'sold_keys': sold_keys,
        'revenue': float(revenue),
        'recent_users': recent_users_data,
    }), 200


# --- Users ---

@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users(user):
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)

    query = User.query.filter(User.id != 1)  # Hide superadmin

    if search:
        query = query.filter(User.email.ilike(f'%{search}%'))

    # Type filter (admin/client)
    type_filter = request.args.get('type', '').strip()
    if type_filter == 'admin':
        query = query.filter(User.is_admin.is_(True))
    elif type_filter == 'client':
        query = query.filter(User.is_admin.is_(False))

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    now = datetime.utcnow()
    users_data = []
    for u in pagination.items:
        u_dict = u.to_dict()

        # Determine activation status
        if u.is_admin:
            u_dict['activation_status'] = 'active'
            u_dict['activation_expires'] = None
        else:
            active_key = ActivationKey.query.filter(
                ActivationKey.user_id == u.id,
                ActivationKey.status == 'activated',
                ActivationKey.expires_at > now,
            ).first()

            if active_key:
                u_dict['activation_status'] = 'active'
                u_dict['activation_expires'] = active_key.expires_at.isoformat()
            else:
                trial = Device.query.filter(
                    Device.user_id == u.id,
                    Device.trial_expires_at > now,
                ).first()
                if trial:
                    u_dict['activation_status'] = 'trial'
                    u_dict['activation_expires'] = trial.trial_expires_at.isoformat()
                else:
                    u_dict['activation_status'] = 'expired'
                    u_dict['activation_expires'] = None

        users_data.append(u_dict)

    # Apply status filter after computing statuses
    if status_filter:
        if status_filter == 'admin':
            users_data = [u for u in users_data if u.get('is_admin')]
        else:
            users_data = [u for u in users_data if u['activation_status'] == status_filter]

    return jsonify({
        'users': users_data,
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
    }), 200


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(admin, user_id):
    if user_id == 1:
        return jsonify({'error': 'User not found'}), 404
    target = User.query.get(user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404

    now = datetime.utcnow()
    devices = Device.query.filter_by(user_id=user_id).all()
    keys = ActivationKey.query.filter_by(user_id=user_id).all()
    databases = ProductDatabase.query.filter_by(user_id=user_id).all()

    # Compute activation status
    user_dict = target.to_dict()
    if target.is_admin:
        user_dict['activation_status'] = 'active'
        user_dict['activation_expires'] = None
    else:
        active_key = ActivationKey.query.filter(
            ActivationKey.user_id == target.id,
            ActivationKey.status == 'activated',
            ActivationKey.expires_at > now,
        ).first()
        if active_key:
            user_dict['activation_status'] = 'active'
            user_dict['activation_expires'] = active_key.expires_at.isoformat()
        else:
            trial = Device.query.filter(
                Device.user_id == target.id,
                Device.trial_expires_at > now,
            ).first()
            if trial:
                user_dict['activation_status'] = 'trial'
                user_dict['activation_expires'] = trial.trial_expires_at.isoformat()
            else:
                user_dict['activation_status'] = 'expired'
                user_dict['activation_expires'] = None

    return jsonify({
        'user': user_dict,
        'devices': [d.to_dict() for d in devices],
        'activation_keys': [k.to_dict() for k in keys],
        'databases': [db_.to_dict() for db_ in databases],
    }), 200


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(admin, user_id):
    if user_id == 1:
        return jsonify({'error': 'User not found'}), 404
    target = User.query.get(user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    if 'is_active' in data:
        target.is_active = bool(data['is_active'])
    if 'is_admin' in data:
        target.is_admin = bool(data['is_admin'])
    if 'password' in data:
        new_password = data['password'].strip()
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        target.password_hash = generate_password_hash(new_password)

    db.session.commit()
    return jsonify(target.to_dict()), 200


@admin_bp.route('/users/<int:user_id>/extend', methods=['POST'])
@admin_required
def extend_license(admin, user_id):
    """Extend user's active key by N days. If expired, restart from now."""
    if user_id == 1:
        return jsonify({'error': 'User not found'}), 404
    target = User.query.get(user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    days = data.get('days', 0)
    if not days or days < 1:
        return jsonify({'error': 'days must be a positive number'}), 400

    now = datetime.utcnow()

    # Find activated key for this user
    key = ActivationKey.query.filter(
        ActivationKey.user_id == user_id,
        ActivationKey.status == 'activated',
    ).first()

    if not key:
        return jsonify({'error': 'User has no activated key'}), 404

    if key.expires_at and key.expires_at > now:
        # Key still active — add days to current expires_at
        key.expires_at = key.expires_at + timedelta(days=days)
        key.duration_days = key.duration_days + days
    else:
        # Key expired — restart from now
        key.activated_at = now
        key.expires_at = now + timedelta(days=days)
        key.duration_days = days

    db.session.commit()
    return jsonify({
        'message': f'License extended by {days} days',
        'key': key.to_dict(),
    }), 200


@admin_bp.route('/users/<int:user_id>/assign-key', methods=['POST'])
@admin_required
def assign_key(admin, user_id):
    """Admin assigns an available/sold key to a specific user."""
    if user_id == 1:
        return jsonify({'error': 'User not found'}), 404
    target = User.query.get(user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    key_id = data.get('key_id')
    if not key_id:
        return jsonify({'error': 'key_id is required'}), 400

    key = ActivationKey.query.get(key_id)
    if not key:
        return jsonify({'error': 'Key not found'}), 404

    if key.status not in ('available', 'sold'):
        return jsonify({'error': 'Ключ уже использован или отозван'}), 400

    now = datetime.utcnow()
    key.user_id = target.id
    key.activated_email = target.email
    key.activated_at = now
    key.expires_at = now + timedelta(days=key.duration_days)
    key.status = 'activated'

    db.session.commit()
    return jsonify({
        'message': 'Ключ успешно назначен',
        'key': key.to_dict(),
    }), 200


# --- Activation Keys ---

@admin_bp.route('/keys', methods=['GET'])
@admin_required
def list_keys(user):
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)

    query = ActivationKey.query

    if status_filter:
        query = query.filter_by(status=status_filter)
    if search:
        query = query.filter(
            db.or_(
                ActivationKey.key_code.ilike(f'%{search}%'),
                ActivationKey.activated_email.ilike(f'%{search}%'),
                ActivationKey.sold_to_name.ilike(f'%{search}%'),
                ActivationKey.sold_to_email.ilike(f'%{search}%'),
            )
        )

    query = query.order_by(ActivationKey.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'keys': [k.to_dict() for k in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
    }), 200


@admin_bp.route('/keys/generate', methods=['POST'])
@admin_required
def generate_keys(admin_user):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    count = data.get('count', 1)
    count = min(max(1, count), 100)  # 1-100 keys at a time
    duration_days = data.get('duration_days', 365)
    sold_to_name = data.get('sold_to_name', '').strip() or None
    sold_to_email = data.get('sold_to_email', '').strip() or None
    sold_price = data.get('sold_price')
    notes = data.get('notes', '').strip() or None

    now = datetime.utcnow()
    initial_status = 'available'
    sold_at = None

    # If sold_to info provided, mark as sold immediately
    if sold_to_name or sold_to_email:
        initial_status = 'sold'
        sold_at = now

    keys = []
    for _ in range(count):
        key = ActivationKey(
            key_code=generate_activation_key(),
            duration_days=duration_days,
            status=initial_status,
            sold_to_name=sold_to_name,
            sold_to_email=sold_to_email,
            sold_at=sold_at,
            sold_price=sold_price,
            notes=notes,
            created_by=admin_user.id,
        )
        db.session.add(key)
        keys.append(key)

    db.session.commit()
    return jsonify({
        'message': f'{len(keys)} key(s) generated',
        'keys': [k.to_dict() for k in keys],
    }), 201


@admin_bp.route('/keys/<int:key_id>', methods=['PUT'])
@admin_required
def update_key(user, key_id):
    key = ActivationKey.query.get(key_id)
    if not key:
        return jsonify({'error': 'Key not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    now = datetime.utcnow()

    if 'status' in data:
        new_status = data['status']
        if new_status == 'revoked':
            # Expire all trials for the user so they become fully expired
            if key.user_id:
                Device.query.filter(
                    Device.user_id == key.user_id,
                    Device.trial_expires_at > now,
                ).update({Device.trial_expires_at: now})
            key.status = 'revoked'
            key.user_id = None
            key.activated_email = None
            key.activated_at = None
            key.expires_at = None
        elif new_status == 'sold' and key.status == 'available':
            key.status = 'sold'
            key.sold_at = now

    if 'sold_to_name' in data:
        key.sold_to_name = data['sold_to_name'].strip() or None
    if 'sold_to_email' in data:
        key.sold_to_email = data['sold_to_email'].strip() or None
    if 'sold_price' in data:
        key.sold_price = data['sold_price']
    if 'notes' in data:
        key.notes = data['notes'].strip() or None
    if 'duration_days' in data:
        new_duration = int(data['duration_days'])
        key.duration_days = new_duration
        # Recalculate expires_at for activated keys
        if key.status == 'activated' and key.activated_at:
            key.expires_at = key.activated_at + timedelta(days=new_duration)

    db.session.commit()
    return jsonify(key.to_dict()), 200


@admin_bp.route('/keys/<int:key_id>', methods=['DELETE'])
@admin_required
def delete_key(user, key_id):
    key = ActivationKey.query.get(key_id)
    if not key:
        return jsonify({'error': 'Key not found'}), 404

    db.session.delete(key)
    db.session.commit()
    return jsonify({'message': 'Key deleted'}), 200
