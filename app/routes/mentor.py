"""
Mentor routes — a logged-in mentor viewing their own profile and their
assigned mentees. A mentor can only see students currently assigned to
them (enforced by filtering on mentor.mentees, never by trusting a
student_id passed in from the client).
"""

from flask import Blueprint, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import Mentor
from app.decorators import role_required

mentor_bp = Blueprint("mentor", __name__, url_prefix="/mentor")


def _current_mentor():
    user_id = int(get_jwt_identity())
    return Mentor.query.filter_by(user_id=user_id).first()


@mentor_bp.route("/me", methods=["GET"])
@jwt_required()
@role_required("mentor")
def get_my_profile():
    mentor = _current_mentor()
    if not mentor:
        return jsonify({"error": "Mentor profile not found"}), 404

    return jsonify({
        "id": mentor.id,
        "mentor_code": mentor.mentor_code,
        "name": mentor.name,
        "email": mentor.user.email,
        "phone": mentor.phone,
        "department": mentor.department,
        "designation": mentor.designation,
        "specialization": mentor.specialization,
        "max_mentee_capacity": mentor.max_mentee_capacity,
        "current_mentee_count": mentor.current_mentee_count,
        "status": mentor.status.value,
    }), 200


@mentor_bp.route("/me/mentees", methods=["GET"])
@jwt_required()
@role_required("mentor")
def get_my_mentees():
    mentor = _current_mentor()
    if not mentor:
        return jsonify({"error": "Mentor profile not found"}), 404

    mentees = [{
        "id": s.id,
        "student_code": s.student_code,
        "name": s.name,
        "department": s.department,
        "batch": s.batch,
        "semester": s.semester,
        "section": s.section,
        "cgpa": s.cgpa,
    } for s in mentor.mentees]

    return jsonify({"mentees": mentees, "count": len(mentees)}), 200


@mentor_bp.route("/me/mentees/<int:student_id>", methods=["GET"])
@jwt_required()
@role_required("mentor")
def get_mentee_detail(student_id):
    mentor = _current_mentor()
    if not mentor:
        return jsonify({"error": "Mentor profile not found"}), 404

    student = next((s for s in mentor.mentees if s.id == student_id), None)
    if not student:
        # Not found OR not this mentor's mentee — same response either way,
        # so we don't leak which student IDs exist.
        abort(404, description="Student not found among your mentees")

    academics = [{
        "semester": r.semester,
        "subject": r.subject,
        "total": r.total,
        "grade": r.grade,
        "grade_point": r.grade_point,
    } for r in student.academic_records]

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
        "cgpa": student.cgpa,
        "academic_records": academics,
    }), 200