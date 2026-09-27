"""
Auth routes
-----------
POST /auth/register  -> student self-registration only (per the requirements
                         doc: Student has "Register/login", Mentor only has
                         "Login" — mentor & admin accounts are created by
                         Admin in the admin routes, not here).
POST /auth/login      -> works for student, mentor, and admin. Returns a JWT
                         with the user's role embedded as a claim, so route
                         guards (see decorators.py) can check permissions
                         without an extra DB lookup on every request.
"""

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token

from app.models import db, User, Student, UserRole

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    required = ["email", "password", "student_code", "name", "department", "batch", "semester"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered"}), 409

    if Student.query.filter_by(student_code=data["student_code"]).first():
        return jsonify({"error": "Student code already in use"}), 409

    user = User(
        email=data["email"],
        password_hash=generate_password_hash(data["password"]),
        role=UserRole.STUDENT,
    )
    db.session.add(user)
    db.session.flush()  # get user.id before creating the linked Student row

    student = Student(
        user_id=user.id,
        student_code=data["student_code"],
        name=data["name"],
        department=data["department"],
        batch=data["batch"],
        semester=data["semester"],
        phone=data.get("phone"),
        section=data.get("section"),
        address=data.get("address"),
        parent_guardian_name=data.get("parent_guardian_name"),
        parent_guardian_phone=data.get("parent_guardian_phone"),
        emergency_contact=data.get("emergency_contact"),
    )
    db.session.add(student)
    db.session.commit()

    return jsonify({"message": "Registered successfully", "student_id": student.id}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.is_active:
        return jsonify({"error": "Account is inactive"}), 403

    # role goes in the token as a custom claim, so downstream routes can
    # check permissions from the token alone
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role.value},
    )

    profile_id = None
    if user.role == UserRole.STUDENT and user.student:
        profile_id = user.student.id
    elif user.role == UserRole.MENTOR and user.mentor:
        profile_id = user.mentor.id
    elif user.role == UserRole.ADMIN and user.admin:
        profile_id = user.admin.id

    return jsonify({
        "access_token": token,
        "role": user.role.value,
        "profile_id": profile_id,
    }), 200