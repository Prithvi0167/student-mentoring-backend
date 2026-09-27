"""
Meeting routes — request -> accept/reject/reschedule workflow.

Student can:
  POST /meetings              -> request a meeting with their mentor
  GET  /meetings               -> list their own meetings

Mentor can:
  GET  /meetings                       -> list meetings with their mentees
  PATCH /meetings/<id>/respond         -> accept / reject / reschedule

A student can only ever create/view meetings tied to their own mentor
relationship; a mentor can only act on meetings tied to their own mentees.
Neither can touch another pair's meeting by guessing an ID.
"""

from datetime import datetime

from flask import Blueprint, request, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.models import db, Student, Mentor, Meeting, MeetingStatus, RequestedBy
from app.decorators import role_required

meeting_bp = Blueprint("meeting", __name__, url_prefix="/meetings")


def _current_student():
    return Student.query.filter_by(user_id=int(get_jwt_identity())).first()


def _current_mentor():
    return Mentor.query.filter_by(user_id=int(get_jwt_identity())).first()


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Student: request a meeting
# ---------------------------------------------------------------------------

@meeting_bp.route("", methods=["POST"])
@jwt_required()
@role_required("student")
def request_meeting():
    student = _current_student()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404
    if not student.mentor:
        return jsonify({"error": "You don't have a mentor assigned yet"}), 400

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    proposed = _parse_datetime(data.get("proposed_datetime"))
    if not proposed:
        return jsonify({"error": "proposed_datetime is required (ISO format, e.g. 2026-10-01T14:30:00)"}), 400

    meeting = Meeting(
        student_id=student.id,
        mentor_id=student.mentor_id,
        requested_by=RequestedBy.STUDENT,
        proposed_datetime=proposed,
        notes=data.get("notes"),
        status=MeetingStatus.PENDING,
    )
    db.session.add(meeting)
    db.session.commit()

    return jsonify({"message": "Meeting requested", "meeting_id": meeting.id}), 201


# ---------------------------------------------------------------------------
# List meetings — works for either role, scoped to their own data
# ---------------------------------------------------------------------------

@meeting_bp.route("", methods=["GET"])
@jwt_required()
@role_required("student", "mentor")
def list_meetings():
    role = get_jwt().get("role")

    if role == "student":
        student = _current_student()
        if not student:
            return jsonify({"error": "Student profile not found"}), 404
        meetings = student.meetings
    else:
        mentor = _current_mentor()
        if not mentor:
            return jsonify({"error": "Mentor profile not found"}), 404
        meetings = mentor.meetings

    return jsonify([_serialize(m) for m in meetings]), 200


def _serialize(m):
    return {
        "id": m.id,
        "student_id": m.student_id,
        "student_name": m.student.name,
        "mentor_id": m.mentor_id,
        "mentor_name": m.mentor.name,
        "requested_by": m.requested_by.value,
        "requested_at": m.requested_at.isoformat(),
        "proposed_datetime": m.proposed_datetime.isoformat(),
        "confirmed_datetime": m.confirmed_datetime.isoformat() if m.confirmed_datetime else None,
        "status": m.status.value,
        "notes": m.notes,
    }


# ---------------------------------------------------------------------------
# Mentor: accept / reject / reschedule
# ---------------------------------------------------------------------------

@meeting_bp.route("/<int:meeting_id>/respond", methods=["PATCH"])
@jwt_required()
@role_required("mentor")
def respond_to_meeting(meeting_id):
    mentor = _current_mentor()
    if not mentor:
        return jsonify({"error": "Mentor profile not found"}), 404

    meeting = next((m for m in mentor.meetings if m.id == meeting_id), None)
    if not meeting:
        abort(404, description="Meeting not found among your requests")

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    action = data.get("action")  # "accept" | "reject" | "reschedule"
    if action not in ("accept", "reject", "reschedule"):
        return jsonify({"error": "action must be one of: accept, reject, reschedule"}), 400

    if action == "accept":
        meeting.status = MeetingStatus.ACCEPTED
        meeting.confirmed_datetime = meeting.proposed_datetime

    elif action == "reject":
        meeting.status = MeetingStatus.REJECTED

    elif action == "reschedule":
        new_time = _parse_datetime(data.get("new_datetime"))
        if not new_time:
            return jsonify({"error": "new_datetime is required for reschedule (ISO format)"}), 400
        meeting.status = MeetingStatus.RESCHEDULED
        meeting.proposed_datetime = new_time
        meeting.confirmed_datetime = None  # student needs to see + implicitly accept the new time

    db.session.commit()
    return jsonify({"message": f"Meeting {action}ed", "meeting": _serialize(meeting)}), 200