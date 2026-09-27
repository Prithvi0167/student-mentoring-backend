"""
Admin routes — manage students & mentors, and handle mentor allocation.

Note: there's no public "create admin" endpoint on purpose — admin accounts
shouldn't be self-serve. Create the first admin with a one-off seed script
(see bottom of this file for a snippet) rather than exposing it over HTTP.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash

from app.models import (
    db, User, Student, Mentor, Admin, MentorAssignment, AcademicRecord,
    UserRole, AssignmentStatus,
)
from app.decorators import role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _current_admin():
    user_id = int(get_jwt_identity())
    return Admin.query.filter_by(user_id=user_id).first()


# ---------------------------------------------------------------------------
# Mentor account management
# ---------------------------------------------------------------------------

@admin_bp.route("/mentors", methods=["POST"])
@jwt_required()
@role_required("admin")
def create_mentor():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    required = ["email", "password", "mentor_code", "name", "department"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Email already registered"}), 409
    if Mentor.query.filter_by(mentor_code=data["mentor_code"]).first():
        return jsonify({"error": "Mentor code already in use"}), 409

    user = User(
        email=data["email"],
        password_hash=generate_password_hash(data["password"]),
        role=UserRole.MENTOR,
    )
    db.session.add(user)
    db.session.flush()

    mentor = Mentor(
        user_id=user.id,
        mentor_code=data["mentor_code"],
        name=data["name"],
        department=data["department"],
        phone=data.get("phone"),
        designation=data.get("designation"),
        specialization=data.get("specialization"),
        max_mentee_capacity=data.get("max_mentee_capacity", 20),
    )
    db.session.add(mentor)
    db.session.commit()

    return jsonify({"message": "Mentor created", "mentor_id": mentor.id}), 201


@admin_bp.route("/mentors", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_mentors():
    mentors = Mentor.query.all()
    return jsonify([{
        "id": m.id,
        "mentor_code": m.mentor_code,
        "name": m.name,
        "department": m.department,
        "status": m.status.value,
        "current_mentee_count": m.current_mentee_count,
        "max_mentee_capacity": m.max_mentee_capacity,
    } for m in mentors]), 200


# ---------------------------------------------------------------------------
# Student management (listing — students self-register via /auth/register)
# ---------------------------------------------------------------------------

@admin_bp.route("/students", methods=["GET"])
@jwt_required()
@role_required("admin")
def list_students():
    students = Student.query.all()
    return jsonify([{
        "id": s.id,
        "student_code": s.student_code,
        "name": s.name,
        "department": s.department,
        "batch": s.batch,
        "semester": s.semester,
        "mentor_id": s.mentor_id,
        "mentor_name": s.mentor.name if s.mentor else None,
        "cgpa": s.cgpa,
    } for s in students]), 200


# ---------------------------------------------------------------------------
# Mentor allocation
# ---------------------------------------------------------------------------

@admin_bp.route("/assign", methods=["POST"])
@jwt_required()
@role_required("admin")
def assign_mentor():
    admin = _current_admin()
    if not admin:
        return jsonify({"error": "Admin profile not found"}), 404

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    student_id = data.get("student_id")
    mentor_id = data.get("mentor_id")
    if not student_id or not mentor_id:
        return jsonify({"error": "student_id and mentor_id are required"}), 400

    student = Student.query.get(student_id)
    mentor = Mentor.query.get(mentor_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    if not mentor:
        return jsonify({"error": "Mentor not found"}), 404
    if not mentor.has_capacity:
        return jsonify({"error": "Mentor is at max mentee capacity"}), 409

    # close out any existing active assignment for this student
    existing = MentorAssignment.query.filter_by(
        student_id=student.id, status=AssignmentStatus.ACTIVE
    ).first()
    if existing:
        existing.status = AssignmentStatus.ENDED
        from datetime import datetime
        existing.ended_date = datetime.utcnow()

    assignment = MentorAssignment(
        student_id=student.id,
        mentor_id=mentor.id,
        assigned_by_admin_id=admin.id,
        status=AssignmentStatus.ACTIVE,
    )
    db.session.add(assignment)

    student.mentor_id = mentor.id  # fast-lookup field stays in sync
    db.session.commit()

    return jsonify({"message": f"{student.name} assigned to {mentor.name}"}), 200


@admin_bp.route("/assignments/<int:student_id>", methods=["GET"])
@jwt_required()
@role_required("admin")
def assignment_history(student_id):
    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    history = [{
        "mentor_id": a.mentor_id,
        "mentor_name": a.mentor.name,
        "assigned_date": a.assigned_date.isoformat(),
        "ended_date": a.ended_date.isoformat() if a.ended_date else None,
        "status": a.status.value,
    } for a in student.assignment_history]

    return jsonify({"student_id": student.id, "history": history}), 200


# ---------------------------------------------------------------------------
# Academic records
# ---------------------------------------------------------------------------

@admin_bp.route("/students/<int:student_id>/academics", methods=["GET"])
@jwt_required()
@role_required("admin")
def get_student_academics(student_id):
    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    records = [{
        "id": r.id,
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

    return jsonify({"student_id": student.id, "records": records, "cgpa": student.cgpa}), 200


@admin_bp.route("/students/<int:student_id>/academics", methods=["POST"])
@jwt_required()
@role_required("admin")
def add_or_update_academic_record(student_id):
    """
    Creates a new record for (student, semester, subject), or updates it if
    one already exists — so re-submitting corrected marks for the same
    subject/semester doesn't create a duplicate row (the unique constraint
    on AcademicRecord would reject a plain insert anyway).
    """
    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    required = ["semester", "subject"]
    missing = [f for f in required if data.get(f) in (None, "")]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    semester = data.get("semester")
    subject = data.get("subject")

    record = AcademicRecord.query.filter_by(
        student_id=student.id, semester=semester, subject=subject
    ).first()

    if not record:
        record = AcademicRecord(student_id=student.id, semester=semester, subject=subject)
        db.session.add(record)

    # Any field left out of the request keeps its previous value (or default
    # 0 for a brand new record) rather than being wiped to null.
    for field in ("internal_marks", "assignment_marks", "practical_marks",
                  "end_semester_marks", "grade", "grade_point"):
        if field in data:
            setattr(record, field, data[field])

    db.session.commit()

    return jsonify({
        "message": "Academic record saved",
        "record": {
            "id": record.id,
            "semester": record.semester,
            "subject": record.subject,
            "internal_marks": record.internal_marks,
            "assignment_marks": record.assignment_marks,
            "practical_marks": record.practical_marks,
            "end_semester_marks": record.end_semester_marks,
            "total": record.total,
            "grade": record.grade,
            "grade_point": record.grade_point,
        }
    }), 200


@admin_bp.route("/academics/<int:record_id>", methods=["DELETE"])
@jwt_required()
@role_required("admin")
def delete_academic_record(record_id):
    record = AcademicRecord.query.get(record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404

    db.session.delete(record)
    db.session.commit()
    return jsonify({"message": "Record deleted"}), 200


# ---------------------------------------------------------------------------
# One-off: run this in a Python shell (flask shell) to create the first admin
# ---------------------------------------------------------------------------
#
# from app.models import db, User, Admin, UserRole
# from werkzeug.security import generate_password_hash
#
# user = User(email="admin@college.edu",
#             password_hash=generate_password_hash("changeme"),
#             role=UserRole.ADMIN)
# db.session.add(user)
# db.session.flush()
# db.session.add(Admin(user_id=user.id, name="Super Admin"))
# db.session.commit()