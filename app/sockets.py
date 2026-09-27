"""
Socket.IO events for real-time student <-> mentor chat.

Auth model: the client connects with its JWT as a query param
(`io(url, { query: { token: accessToken } })` on the JS side). We decode
it ONCE at connect time and cache the resulting user_id/role in
`connected_users`, keyed by request.sid — not re-read from request.args
on every event, since that isn't reliable after a WebSocket upgrade.

Room naming: each student-mentor pair gets its own room,
"chat_<student_id>_<mentor_id>", so messages only ever broadcast to the
two people in that relationship.
"""

from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import join_room, emit, disconnect

from app.extensions import socketio
from app.models import db, Student, Mentor, Message, RequestedBy

# sid -> {"user_id": int, "role": "student" | "mentor"}
connected_users = {}


def _room_name(student_id, mentor_id):
    return f"chat_{student_id}_{mentor_id}"


@socketio.on("connect")
def handle_connect():
    token = request.args.get("token")
    if not token:
        disconnect()
        return False

    try:
        claims = decode_token(token)
    except Exception:
        disconnect()
        return False

    connected_users[request.sid] = {
        "user_id": int(claims["sub"]),
        "role": claims.get("role"),
    }
    return True


@socketio.on("disconnect")
def handle_disconnect():
    connected_users.pop(request.sid, None)


@socketio.on("join")
def handle_join(data):
    identity = connected_users.get(request.sid)
    if not identity:
        emit("error", {"message": "Not authenticated"})
        return

    user_id = identity["user_id"]
    role = identity["role"]

    student_id = data.get("student_id")
    mentor_id = data.get("mentor_id")
    if not student_id or not mentor_id:
        emit("error", {"message": "student_id and mentor_id are required"})
        return

    authorized = False
    if role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        authorized = bool(student and student.id == student_id and student.mentor_id == mentor_id)
    elif role == "mentor":
        mentor = Mentor.query.filter_by(user_id=user_id).first()
        authorized = bool(mentor and mentor.id == mentor_id and
                           any(s.id == student_id for s in mentor.mentees))

    if not authorized:
        emit("error", {"message": "Not authorized to join this chat"})
        return

    join_room(_room_name(student_id, mentor_id))
    emit("joined", {"room": _room_name(student_id, mentor_id)})


@socketio.on("send_message")
def handle_send_message(data):
    identity = connected_users.get(request.sid)
    if not identity:
        emit("error", {"message": "Not authenticated"})
        return

    user_id = identity["user_id"]
    role = identity["role"]

    student_id = data.get("student_id")
    mentor_id = data.get("mentor_id")
    content = (data.get("content") or "").strip()

    if not student_id or not mentor_id or not content:
        emit("error", {"message": "student_id, mentor_id, and content are required"})
        return

    if role == "student":
        student = Student.query.filter_by(user_id=user_id).first()
        if not student or student.id != student_id or student.mentor_id != mentor_id:
            emit("error", {"message": "Not authorized to send in this chat"})
            return
        sender_role = RequestedBy.STUDENT
    elif role == "mentor":
        mentor = Mentor.query.filter_by(user_id=user_id).first()
        if not mentor or mentor.id != mentor_id or not any(s.id == student_id for s in mentor.mentees):
            emit("error", {"message": "Not authorized to send in this chat"})
            return
        sender_role = RequestedBy.MENTOR
    else:
        emit("error", {"message": "Unrecognized role"})
        return

    message = Message(
        student_id=student_id,
        mentor_id=mentor_id,
        sender_role=sender_role,
        content=content,
    )
    db.session.add(message)
    db.session.commit()

    emit("new_message", {
        "id": message.id,
        "student_id": student_id,
        "mentor_id": mentor_id,
        "sender_role": sender_role.value,
        "content": content,
        "sent_at": message.sent_at.isoformat(),
    }, room=_room_name(student_id, mentor_id))