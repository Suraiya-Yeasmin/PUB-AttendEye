"""Converts ORM rows to API dictionaries. Biometric fields are deliberately never included."""
from datetime import datetime

from .models import (Attendance, ClassCourse, ClassSession, RecognitionEvent, Student, Teacher)
from .services.trustscore import DECISION_LABELS


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def teacher_out(t: Teacher) -> dict:
    return {"id": t.id, "username": t.username, "email": t.email, "full_name": t.full_name,
            "role": t.role, "is_active": t.is_active, "created_at": iso(t.created_at)}


def student_out(s: Student) -> dict:
    tpl = s.template
    return {"id": s.id, "student_id": s.student_id, "full_name": s.full_name, "department": s.department,
            "section": s.section, "email": s.email, "status": s.status,
            "biometric_consent": s.biometric_consent, "face_enrolled": tpl is not None,
            "enrolled_samples": tpl.sample_count if tpl else 0,
            "template_created_at": iso(tpl.created_at) if tpl else None,
            "created_at": iso(s.created_at)}


def class_out(c: ClassCourse) -> dict:
    return {"id": c.id, "code": c.code, "name": c.name, "section": c.section, "department": c.department,
            "teacher_id": c.teacher_id, "teacher_name": c.teacher.full_name, "is_active": c.is_active,
            "roster_size": len(c.students), "created_at": iso(c.created_at)}


def session_out(s: ClassSession, present: int | None = None) -> dict:
    c = s.course
    d = {"id": s.id, "class_id": s.class_id, "course_code": c.code, "course_name": c.name,
         "section": c.section, "teacher_name": c.teacher.full_name,
         "session_date": s.session_date.isoformat(), "start_time": s.start_time, "end_time": s.end_time,
         "status": s.status, "started_at": iso(s.started_at), "ended_at": iso(s.ended_at),
         "roster_size": len(c.students)}
    if present is not None:
        d["present_count"] = present
    return d


def attendance_out(a: Attendance) -> dict:
    s, sess = a.student, a.session
    return {"id": a.id, "session_id": a.session_id, "student_pk": a.student_pk, "student_id": s.student_id,
            "student_name": s.full_name, "course_code": sess.course.code, "course_name": sess.course.name,
            "section": sess.course.section, "session_date": sess.session_date.isoformat(),
            "timestamp": iso(a.timestamp), "method": a.method, "status": a.status,
            "review_status": a.review_status, "similarity": a.similarity, "corrected": a.corrected,
            "note": a.note}


def event_out(e: RecognitionEvent) -> dict:
    s = e.student
    return {"id": e.id, "session_id": e.session_id, "timestamp": iso(e.timestamp),
            "student_pk": e.student_pk, "student_id": s.student_id if s else None,
            "student_name": s.full_name if s else None, "similarity": e.similarity,
            "runner_up_similarity": e.runner_up_similarity, "quality_status": e.quality_status,
            "decision": e.decision, "decision_label": DECISION_LABELS.get(e.decision, e.decision),
            "reason": e.reason, "review_status": e.review_status, "reviewed_at": iso(e.reviewed_at),
            "has_thumbnail": bool(e.thumbnail), "processing_ms": e.processing_ms}
