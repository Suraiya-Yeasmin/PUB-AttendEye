"""Database schema. All timestamps are naive UTC; the API serialises them with a trailing 'Z'."""
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary,
                        String, Table, Column, Text, UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(16), default="teacher")  # 'admin' | 'teacher'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    session_epoch: Mapped[int] = mapped_column(Integer, default=0)  # bump to revoke tokens
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(80))
    section: Mapped[str] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | inactive
    # not_requested | granted | declined | withdrawn
    biometric_consent: Mapped[str] = mapped_column(String(16), default="not_requested")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    template: Mapped["FaceTemplate | None"] = relationship(
        back_populates="student", cascade="all, delete-orphan", uselist=False)


class FaceTemplate(Base):
    """One averaged, encrypted embedding per student. Never serialised to the API."""
    __tablename__ = "face_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_pk: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), unique=True)
    embedding_enc: Mapped[bytes] = mapped_column(LargeBinary)
    model_name: Mapped[str] = mapped_column(String(80))
    sample_count: Mapped[int] = mapped_column(Integer)
    min_quality_sharpness: Mapped[float | None] = mapped_column(Float, nullable=True)
    consent_recorded_at: Mapped[datetime] = mapped_column(DateTime)
    consent_recorded_by: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    student: Mapped[Student] = relationship(back_populates="template")


class_students = Table(
    "class_students", Base.metadata,
    Column("class_id", ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
    Column("student_pk", ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
)


class ClassCourse(Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("code", "section", "teacher_id", name="uq_class_code_section_teacher"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    section: Mapped[str] = mapped_column(String(32))
    department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    teacher: Mapped[Teacher] = relationship()
    students: Mapped[list[Student]] = relationship(secondary=class_students)
    sessions: Mapped[list["ClassSession"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class ClassSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    session_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[str] = mapped_column(String(5))  # HH:MM local
    end_time: Mapped[str] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(12), default="scheduled")  # scheduled|active|completed|cancelled
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    course: Mapped[ClassCourse] = relationship(back_populates="sessions")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_pk", "session_id", name="uq_attendance_student_session"),
                      Index("ix_attendance_session", "session_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    student_pk: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    method: Mapped[str] = mapped_column(String(16))  # face | face_review | manual
    status: Mapped[str] = mapped_column(String(10), default="present")  # present | late | excused
    review_status: Mapped[str] = mapped_column(String(16), default="not_required")  # not_required | teacher_confirmed
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    recognition_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)

    student: Mapped[Student] = relationship()
    session: Mapped[ClassSession] = relationship()


class RecognitionEvent(Base):
    """A persisted recognition outcome that matters (accepted / review / unknown / duplicate)."""
    __tablename__ = "recognition_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    student_pk: Mapped[int | None] = mapped_column(ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    runner_up_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(24), default="ok")
    face_count: Mapped[int] = mapped_column(Integer, default=1)
    decision: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(400))
    review_status: Mapped[str] = mapped_column(String(12), default="none")  # none|pending|confirmed|rejected|unknown
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processing_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    thumbnail: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # only while review pending

    student: Mapped[Student | None] = relationship()
    session: Mapped[ClassSession] = relationship()


class ReviewEvent(Base):
    __tablename__ = "review_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    recognition_event_id: Mapped[int] = mapped_column(ForeignKey("recognition_events.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    action: Mapped[str] = mapped_column(String(16))  # confirm | reject | unknown | keep_pending
    outcome: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON, never biometric data
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EvaluationSample(Base):
    """A labelled test capture used to measure the real recognition performance."""
    __tablename__ = "evaluation_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    truth_student_pk: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = not enrolled
    predicted_student_pk: Mapped[int | None] = mapped_column(Integer, nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String(24))
    quality_status: Mapped[str] = mapped_column(String(24))
    processing_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accept_threshold: Mapped[float] = mapped_column(Float)
    review_threshold: Mapped[float] = mapped_column(Float)
