"""
Student routes — everything a logged-in student can do to their own data.
All routes are scoped to the logged-in student via the JWT identity; a
student can never pass another student's ID to see someone else's data.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import db, Student
from app.decorators import role_required

student_bp = Blueprint("student", __name__, url_prefix="/student")

# Fields a student is allowed to edit about themselves. Deliberately excludes
# student_code, department, batch, semester, section, mentor_id — those are
# admin/academic-office controlled, not self-service.
EDITABLE_FIELDS = [
    "phone", "address", "parent_guardian_name",
    "parent_guardian_phone", "emergency_contact",
]


def _current_student():
    """Resolve the Student row for whoever the JWT belongs to."""
    user_id = int(get_jwt_identity())
    return Student.query.filter_by(user_id=user_id).first()


@student_bp.route("/me", methods=["GET"])
@jwt_required()
@role_required("student")
def get_my_profile():
    student = _current_student()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    return jsonify({
        "id": student.id,
        "student_code": student.student_code,
        "name": student.name,
        "email": student.user.email,
        "phone": student.phone,
        "department": student.department,
        "batch": student.batch,
        "semester": student.semester,
        "section": student.section,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
        "address": student.address,
        "parent_guardian_name": student.parent_guardian_name,
        "parent_guardian_phone": student.parent_guardian_phone,
        "emergency_contact": student.emergency_contact,
        "cgpa": student.cgpa,
    }), 200


@student_bp.route("/me", methods=["PUT"])
@jwt_required()
@role_required("student")
def update_my_profile():
    student = _current_student()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    for field in EDITABLE_FIELDS:
        if field in data:
            setattr(student, field, data[field])

    db.session.commit()
    return jsonify({"message": "Profile updated"}), 200


@student_bp.route("/me/mentor", methods=["GET"])
@jwt_required()
@role_required("student")
def get_my_mentor():
    student = _current_student()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    if not student.mentor:
        return jsonify({"message": "No mentor assigned yet"}), 200

    m = student.mentor
    return jsonify({
        "id": m.id,
        "name": m.name,
        "email": m.user.email,
        "phone": m.phone,
        "department": m.department,
        "designation": m.designation,
        "specialization": m.specialization,
    }), 200


@student_bp.route("/me/academics", methods=["GET"])
@jwt_required()
@role_required("student")
def get_my_academics():
    student = _current_student()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    records = [{
        "semester": r.semester,
        "subject": r.subject,
        "internal_marks": r.internal_marks,
        "assignment_marks": r.assignment_marks,
        "practical_marks": r.practical_marks,
        "end_semester_marks": r.end_semester_marks,
        "total": r.total,
        "grade": r.grade,
        "grade_point": r.grade_point,
    } for r in student.academic_records]

    return jsonify({
        "records": records,
        "cgpa": student.cgpa,
    }), 200