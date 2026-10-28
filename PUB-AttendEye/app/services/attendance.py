"""Single entry point for creating attendance rows, used by recognition, review and manual marking."""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Attendance, ClassSession, Student


class DuplicateAttendance(Exception):
    def __init__(self, existing: Attendance | None = None):
        self.existing = existing


def roster_pks(course) -> set[int]:
    return {s.id for s in course.students}


def present_count(db: Session, session_id: int) -> int:
    return db.query(Attendance).filter(Attendance.session_id == session_id).count()


def record_attendance(db: Session, session: ClassSession, student: Student, *, method: str,
                      teacher_id: int | None = None, status: str = "present", similarity: float | None = None,
                      event_id: int | None = None, review_status: str = "not_required",
                      note: str | None = None) -> Attendance:
    """Creates one attendance row. Re-validates session and student; the unique constraint on
    (student_pk, session_id) is the final guard against duplicates (also under concurrency)."""
    if session.status != "active":
        raise HTTPException(409, "This session is not active. Attendance cannot be recorded.")
    if student.status != "active":
        raise HTTPException(409, "This student record is deactivated.")
    att = Attendance(session_id=session.id, student_pk=student.id, method=method, status=status,
                     similarity=similarity, recognition_event_id=event_id, review_status=review_status,
                     created_by=teacher_id, note=note)
    try:
        with db.begin_nested():  # savepoint so a duplicate does not poison the outer transaction
            db.add(att)
            db.flush()
    except IntegrityError:
        existing = (db.query(Attendance).filter_by(session_id=session.id, student_pk=student.id).first())
        raise DuplicateAttendance(existing)
    return att
