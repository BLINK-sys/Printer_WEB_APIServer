from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..models.user import User


def jwt_required_custom(fn):
    """Verify JWT and ensure user is active."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user.is_active:
            return jsonify({'error': 'Account disabled'}), 403
        return fn(user, *args, **kwargs)
    return wrapper


def admin_required(fn):
    """Verify JWT and ensure user is admin."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = User.query.get(int(user_id))
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user.is_active:
            return jsonify({'error': 'Account disabled'}), 403
        if not user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return fn(user, *args, **kwargs)
    return wrapper
