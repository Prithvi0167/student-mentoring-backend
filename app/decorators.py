"""
role_required — a decorator that restricts a route to specific roles.

Usage:
    @student_bp.route("/me")
    @jwt_required()
    @role_required("student")
    def get_my_profile():
        ...

Reads the "role" claim set at login time (see routes/auth.py) — no extra
database query needed just to check permissions.
"""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt


def role_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            if claims.get("role") not in allowed_roles:
                return jsonify({"error": "Forbidden: insufficient role"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator