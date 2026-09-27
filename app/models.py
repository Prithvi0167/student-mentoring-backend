"""
Student Mentoring System — Database Models
Stack: Flask + SQLAlchemy

Design notes
------------
- `User` is the auth/identity table (login, role). `Student`, `Mentor`, and
  `Admin` each hold a one-to-one profile linked back to a User, so login
  logic stays in one place and profile logic stays separate per role.
- `Student.mentor_id` gives fast "who is my current mentor" lookups.
  `MentorAssignment` is a separate history table so re-assignments by Admin
  are auditable (who assigned whom, when, and whether it's still active) —
  this matches the doc's explicit "Mentor allocation" module.
- `AcademicRecord` is one row per (student, semester, subject). SGPA/CGPA
  are computed from these rather than stored redundantly, so they can never
  drift out of sync with the underlying marks.
- `Meeting` covers the full request → accept/reject/reschedule workflow.
"""

from datetime import datetime, date
import enum

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum as SqlEnum

db = SQLAlchemy()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(enum.Enum):
    STUDENT = "student"
    MENTOR = "mentor"
    ADMIN = "admin"


class MentorStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AssignmentStatus(enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"


class MeetingStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RequestedBy(enum.Enum):
    STUDENT = "student"
    MENTOR = "mentor"


# ---------------------------------------------------------------------------
# User (auth / identity)
# ---------------------------------------------------------------------------

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(SqlEnum(UserRole), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    student = db.relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    mentor = db.relationship("Mentor", back_populates="user", uselist=False, cascade="all, delete-orphan")
    admin = db.relationship("Admin", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} ({self.role.value})>"


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------

class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    student_code = db.Column(db.String(30), unique=True, nullable=False, index=True)  # e.g. roll number
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    department = db.Column(db.String(100), nullable=False)
    batch = db.Column(db.String(20), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10))
    date_of_birth = db.Column(db.Date)
    address = db.Column(db.Text)
    parent_guardian_name = db.Column(db.String(120))
    parent_guardian_phone = db.Column(db.String(20))
    emergency_contact = db.Column(db.String(20))

    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id"), nullable=True)  # current mentor, fast lookup

    user = db.relationship("User", back_populates="student")
    mentor = db.relationship("Mentor", back_populates="mentees", foreign_keys=[mentor_id])
    academic_records = db.relationship("AcademicRecord", back_populates="student", cascade="all, delete-orphan")
    assignment_history = db.relationship("MentorAssignment", back_populates="student", cascade="all, delete-orphan")
    meetings = db.relationship("Meeting", back_populates="student", cascade="all, delete-orphan")
    messages = db.relationship("Message", back_populates="student", cascade="all, delete-orphan")

    @property
    def cgpa(self):
        """Average SGPA across all semesters with recorded academics."""
        semesters = {r.semester for r in self.academic_records}
        if not semesters:
            return None
        sgpas = [self.sgpa(sem) for sem in semesters]
        sgpas = [s for s in sgpas if s is not None]
        return round(sum(sgpas) / len(sgpas), 2) if sgpas else None

    def sgpa(self, semester):
        """Simple average of per-subject grade points for one semester.
        Swap in a credit-weighted formula here if subjects carry credits."""
        records = [r for r in self.academic_records if r.semester == semester]
        if not records:
            return None
        points = [r.grade_point for r in records if r.grade_point is not None]
        return round(sum(points) / len(points), 2) if points else None

    def __repr__(self):
        return f"<Student {self.student_code} {self.name}>"


# ---------------------------------------------------------------------------
# Mentor
# ---------------------------------------------------------------------------

class Mentor(db.Model):
    __tablename__ = "mentors"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    mentor_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    department = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(100))
    specialization = db.Column(db.String(150))
    max_mentee_capacity = db.Column(db.Integer, default=20, nullable=False)
    status = db.Column(SqlEnum(MentorStatus), default=MentorStatus.ACTIVE, nullable=False)

    user = db.relationship("User", back_populates="mentor")
    mentees = db.relationship("Student", back_populates="mentor", foreign_keys=[Student.mentor_id])
    assignment_history = db.relationship("MentorAssignment", back_populates="mentor", cascade="all, delete-orphan")
    meetings = db.relationship("Meeting", back_populates="mentor", cascade="all, delete-orphan")
    messages = db.relationship("Message", back_populates="mentor", cascade="all, delete-orphan")

    @property
    def current_mentee_count(self):
        return len(self.mentees)

    @property
    def has_capacity(self):
        return self.current_mentee_count < self.max_mentee_capacity

    def __repr__(self):
        return f"<Mentor {self.mentor_code} {self.name}>"


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)

    user = db.relationship("User", back_populates="admin")

    def __repr__(self):
        return f"<Admin {self.name}>"


# ---------------------------------------------------------------------------
# Mentor allocation history (Admin: Student -> Mentor)
# ---------------------------------------------------------------------------

class MentorAssignment(db.Model):
    __tablename__ = "mentor_assignments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id"), nullable=False)
    assigned_by_admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)

    assigned_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(SqlEnum(AssignmentStatus), default=AssignmentStatus.ACTIVE, nullable=False)

    student = db.relationship("Student", back_populates="assignment_history")
    mentor = db.relationship("Mentor", back_populates="assignment_history")
    assigned_by = db.relationship("Admin")

    def __repr__(self):
        return f"<MentorAssignment student={self.student_id} mentor={self.mentor_id} {self.status.value}>"


# ---------------------------------------------------------------------------
# Academic performance
# ---------------------------------------------------------------------------

class AcademicRecord(db.Model):
    __tablename__ = "academic_records"
    __table_args__ = (
        db.UniqueConstraint("student_id", "semester", "subject", name="uq_student_semester_subject"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)

    semester = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    internal_marks = db.Column(db.Float, default=0)
    assignment_marks = db.Column(db.Float, default=0)
    practical_marks = db.Column(db.Float, default=0)
    end_semester_marks = db.Column(db.Float, default=0)
    grade = db.Column(db.String(5))          # e.g. "A+", "B"
    grade_point = db.Column(db.Float)         # e.g. 9.0 — used to compute SGPA/CGPA

    student = db.relationship("Student", back_populates="academic_records")

    @property
    def total(self):
        return (self.internal_marks or 0) + (self.assignment_marks or 0) \
            + (self.practical_marks or 0) + (self.end_semester_marks or 0)

    def __repr__(self):
        return f"<AcademicRecord {self.student_id} sem{self.semester} {self.subject}>"


# ---------------------------------------------------------------------------
# Meeting scheduling
# ---------------------------------------------------------------------------

class Meeting(db.Model):
    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id"), nullable=False)

    requested_by = db.Column(SqlEnum(RequestedBy), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    proposed_datetime = db.Column(db.DateTime, nullable=False)
    confirmed_datetime = db.Column(db.DateTime, nullable=True)  # set once accepted/rescheduled
    status = db.Column(SqlEnum(MeetingStatus), default=MeetingStatus.PENDING, nullable=False)
    notes = db.Column(db.Text)

    student = db.relationship("Student", back_populates="meetings")
    mentor = db.relationship("Mentor", back_populates="meetings")

    def __repr__(self):
        return f"<Meeting student={self.student_id} mentor={self.mentor_id} {self.status.value}>"


# ---------------------------------------------------------------------------
# Chat (real-time, student <-> mentor)
# ---------------------------------------------------------------------------

class Message(db.Model):
    """One row per chat message. Delivered live via Flask-SocketIO (step 2);
    this table is the persistence layer so history survives reconnects/reloads."""
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id"), nullable=False, index=True)

    sender_role = db.Column(SqlEnum(RequestedBy), nullable=False)  # who sent it: STUDENT or MENTOR
    content = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    student = db.relationship("Student", back_populates="messages")
    mentor = db.relationship("Mentor", back_populates="messages")

    def __repr__(self):
        return f"<Message {self.sender_role.value} student={self.student_id} mentor={self.mentor_id}>"