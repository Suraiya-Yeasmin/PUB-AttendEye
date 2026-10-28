from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.demo import scope_students
from ..deps import accessible_class_ids, current_teacher, get_session
from ..models import Attendance, ClassCourse, ClassSession, FaceTemplate, RecognitionEvent, Student, Teacher
from ..serializers import event_out, session_out
from .reports import _pct, _session_rows

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(session_id: int | None = Query(None), t: Teacher = Depends(current_teacher),
              db: Session = Depends(get_db)):
    cids = accessible_class_ids(db, t) or [0]
    sessions_q = db.query(ClassSession).filter(ClassSession.class_id.in_(cids))
    total_students = scope_students(db.query(Student), t).filter(Student.status == "active").count()
    enrolled = (db.query(FaceTemplate).join(Student, Student.id == FaceTemplate.student_pk)
                .filter(Student.status == "active"))
    enrolled = scope_students(enrolled, t).count()

    selected = None
    if session_id:
        selected = get_session(db, t, session_id)
    else:
        selected = (sessions_q.filter(ClassSession.status == "active")
                    .order_by(ClassSession.started_at.desc()).first()
                    or sessions_q.filter(ClassSession.status == "completed")
                    .order_by(ClassSession.session_date.desc(), ClassSession.start_time.desc()).first())

    today = date.today()
    glance = {"classes": db.query(ClassCourse).filter(ClassCourse.id.in_(cids)).count(),
              "sessions": sessions_q.count(),
              "sessions_today": sessions_q.filter(ClassSession.session_date == today).count(),
              "checkins_today": (db.query(Attendance).join(ClassSession, ClassSession.id == Attendance.session_id)
                                 .filter(ClassSession.class_id.in_(cids), ClassSession.session_date == today).count())}
    cards = {"total_students": total_students, "face_enrolled": enrolled, "present": None, "absent": None,
             "pending_reviews": 0, "unknown_detected": 0, "duplicates_prevented": 0}
    cards["pending_reviews"] = (db.query(RecognitionEvent).join(ClassSession, ClassSession.id == RecognitionEvent.session_id)
                                .filter(ClassSession.class_id.in_(cids), RecognitionEvent.review_status == "pending").count())
    overview = None
    activity = []
    if selected:
        recs = db.query(Attendance).filter_by(session_id=selected.id).all()
        roster = len(selected.course.students)
        present = sum(1 for r in recs if r.status in ("present", "late"))
        excused = sum(1 for r in recs if r.status == "excused")
        cards["present"] = len(recs)
        row = _session_rows(db, [selected])[0]  # same definitions as Reports (pending review is not absent)
        cards["absent"] = row["absent"]
        cards["pending_session"] = row["pending_review"]
        ev = dict(db.query(RecognitionEvent.decision, func.count(RecognitionEvent.id))
                  .filter_by(session_id=selected.id).group_by(RecognitionEvent.decision).all())
        cards["unknown_detected"] = ev.get("unknown", 0)
        cards["duplicates_prevented"] = ev.get("duplicate", 0)
        overview = {"present": present, "excused": excused, "absent": row["absent"] or 0, "pending_review": row["pending_review"],
                    "roster_size": roster, "late": sum(1 for r in recs if r.status == "late")}
        activity = [event_out(e) for e in db.query(RecognitionEvent).filter_by(session_id=selected.id)
                    .order_by(RecognitionEvent.id.desc()).limit(8).all()]

    recent = (sessions_q.order_by(ClassSession.session_date.desc(), ClassSession.start_time.desc()).limit(8).all())
    counts = dict(db.query(Attendance.session_id, func.count(Attendance.id))
                  .filter(Attendance.session_id.in_([s.id for s in recent] or [0])).group_by(Attendance.session_id).all())
    trend_sessions = (sessions_q.filter(ClassSession.status.in_(["active", "completed"]))
                      .order_by(ClassSession.session_date.desc(), ClassSession.start_time.desc()).limit(12).all())
    trend = [{"label": f"{r['course_code']} {r['session_date'][5:]}", "percentage": r["percentage"],
              "present": r["present"], "roster_size": r["roster_size"]}
             for r in reversed(_session_rows(db, trend_sessions))]
    startable = (sessions_q.filter(ClassSession.status == "scheduled")
                 .order_by(ClassSession.session_date, ClassSession.start_time).limit(15).all())
    return {
        "cards": cards, "glance": glance,
        "selected_session": session_out(selected, cards["present"]) if selected else None,
        "overview": overview, "activity": activity, "trend": trend,
        "recent_sessions": [session_out(s, counts.get(s.id, 0)) for s in recent],
        "startable_sessions": [session_out(s) for s in startable],
        "empty": {"no_students": total_students == 0,
                  "no_classes": db.query(ClassCourse).filter(ClassCourse.id.in_(cids)).count() == 0,
                  "no_sessions": sessions_q.count() == 0},
        "today": date.today().isoformat(),
    }
