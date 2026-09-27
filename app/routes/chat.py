"""
Chat REST routes — history only. Live sending/receiving happens over
Socket.IO (see sockets.py); this endpoint is just for loading past
messages when a chat window first opens.
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.models import Student, Mentor, Message
from app.decorators import role_required

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


@chat_bp.route("/<int:student_id>/<int:mentor_id>/history", methods=["GET"])
@jwt_required()
@role_required("student", "mentor")
def get_chat_history(student_id, mentor_id):
    role = get_jwt().get("role")
    user_id = int(get_jwt_identity())

    if role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        if not student or student.id != student_id or student.mentor_id != mentor_id:
            return jsonify({"error": "Not authorized to view this chat"}), 403
    else:
        mentor = Mentor.query.filter_by(user_id=user_id).first()
        if not mentor or mentor.id != mentor_id or not any(s.id == student_id for s in mentor.mentees):
            return jsonify({"error": "Not authorized to view this chat"}), 403

    messages = (
        Message.query
        .filter_by(student_id=student_id, mentor_id=mentor_id)
        .order_by(Message.sent_at.asc())
        .all()
    )

    return jsonify([{
        "id": m.id,
        "sender_role": m.sender_role.value,
        "content": m.content,
        "sent_at": m.sent_at.isoformat(),
        "is_read": m.is_read,
    } for m in messages]), 200