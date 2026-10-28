from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_teacher, get_course, get_session
from ..models import Attendance, ClassCourse, ClassSession, RecognitionEvent, Student, Teacher, utcnow
from ..schemas import ClassIn, RosterBySectionIn, RosterIn, SessionIn
from ..serializers import attendance_out, class_out, event_out, iso, session_out, student_out
from ..services.audit import audit
from ..services.demo import scope_students

router = APIRouter(prefix="/api", tags=["classes"])


# ------------------------------------------------------------------ classes
@router.get("/classes")
def list_classes(t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    q = db.query(ClassCourse)
    if t.role != "admin":
        q = q.filter(ClassCourse.teacher_id == t.id)
    return {"items": [class_out(c) for c in q.order_by(ClassCourse.code, ClassCourse.section).all()]}


def _owner(db: Session, t: Teacher, body: ClassIn) -> int:
    if body.teacher_id and body.teacher_id != t.id:
        if t.role != "admin":
            raise HTTPException(403, "Only administrators can assign a class to another teacher.")
        if not db.get(Teacher, body.teacher_id):
            raise HTTPException(404, "Teacher not found.")
        return body.teacher_id
    return t.id


@router.post("/classes", status_code=201)
def create_class(body: ClassIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    owner = _owner(db, t, body)
    if db.query(ClassCourse).filter(func.lower(ClassCourse.code) == body.code.lower(),
                                    func.lower(ClassCourse.section) == body.section.lower(),
                                    ClassCourse.teacher_id == owner).first():
        raise HTTPException(409, "A class with this course code and section already exists.")
    c = ClassCourse(code=body.code, name=body.name, section=body.section, department=body.department,
                    teacher_id=owner)
    db.add(c)
    db.flush()
    audit(db, t.id, "class_create", "class", c.id)
    db.commit()
    return class_out(c)


@router.put("/classes/{class_id}")
def update_class(class_id: int, body: ClassIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    c = get_course(db, t, class_id)
    owner = _owner(db, t, body) if body.teacher_id else c.teacher_id
    clash = db.query(ClassCourse).filter(func.lower(ClassCourse.code) == body.code.lower(),
                                         func.lower(ClassCourse.section) == body.section.lower(),
                                         ClassCourse.teacher_id == owner, ClassCourse.id != c.id).first()
    if clash:
        raise HTTPException(409, "A class with this course code and section already exists.")
    c.code, c.name, c.section, c.department, c.teacher_id = body.code, body.name, body.section, body.department, owner
    audit(db, t.id, "class_update", "class", c.id)
    db.commit()
    return class_out(c)


@router.get("/classes/{class_id}")
def class_detail(class_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    c = get_course(db, t, class_id)
    out = class_out(c)
    out["roster"] = [student_out(s) for s in sorted(c.students, key=lambda s: s.full_name)]
    return out


@router.put("/classes/{class_id}/roster")
def set_roster(class_id: int, body: RosterIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    c = get_course(db, t, class_id)
    students = db.query(Student).filter(Student.id.in_(body.student_pks)).all() if body.student_pks else []
    c.students = students
    audit(db, t.id, "roster_set", "class", c.id, size=len(students))
    db.commit()
    return class_out(c)


@router.post("/classes/{class_id}/roster/by-section")
def roster_by_section(class_id: int, body: RosterBySectionIn, t: Teacher = Depends(current_teacher),
                      db: Session = Depends(get_db)):
    c = get_course(db, t, class_id)
    q = scope_students(db.query(Student), t).filter(Student.status == "active", func.lower(Student.section) == body.section.lower())
    if body.department:
        q = q.filter(Student.department == body.department)
    have = {s.id for s in c.students}
    added = [s for s in q.all() if s.id not in have]
    c.students.extend(added)
    audit(db, t.id, "roster_add_section", "class", c.id, added=len(added))
    db.commit()
    return {"added": len(added), "roster_size": len(c.students)}


# ----------------------------------------------------------------- sessions
@router.get("/sessions")
def list_sessions(class_id: int | None = None, status: str = "", date_from: str = "", date_to: str = "",
                  limit: int = Query(200, le=500), t: Teacher = Depends(current_teacher),
                  db: Session = Depends(get_db)):
    q = db.query(ClassSession).join(ClassCourse)
    if t.role != "admin":
        q = q.filter(ClassCourse.teacher_id == t.id)
    if class_id:
        q = q.filter(ClassSession.class_id == class_id)
    if status:
        q = q.filter(ClassSession.status == status)
    try:
        if date_from:
            q = q.filter(ClassSession.session_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        if date_to:
            q = q.filter(ClassSession.session_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
    except ValueError:
        raise HTTPException(400, "Dates must use YYYY-MM-DD.")
    rows = q.order_by(ClassSession.session_date.desc(), ClassSession.start_time.desc()).limit(limit).all()
    counts = dict(db.query(Attendance.session_id, func.count(Attendance.id))
                  .filter(Attendance.session_id.in_([r.id for r in rows] or [0]))
                  .group_by(Attendance.session_id).all())
    return {"items": [session_out(s, counts.get(s.id, 0)) for s in rows]}


@router.post("/sessions", status_code=201)
def create_session(body: SessionIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    c = get_course(db, t, body.class_id)
    if body.end_time <= body.start_time:
        raise HTTPException(422, "End time must be later than start time.")
    if db.query(ClassSession).filter_by(class_id=c.id, session_date=body.session_date,
                                        start_time=body.start_time).first():
        raise HTTPException(409, "A session for this class already exists at that date and time.")
    s = ClassSession(class_id=c.id, session_date=body.session_date, start_time=body.start_time,
                     end_time=body.end_time)
    db.add(s)
    db.flush()
    audit(db, t.id, "session_create", "session", s.id)
    db.commit()
    return session_out(s, 0)


def _transition(db, t, session_id, allowed_from, new_status, action):
    s = get_session(db, t, session_id)
    if s.status not in allowed_from:
        raise HTTPException(409, f"A {s.status} session cannot be {action}.")
    return s


def _ensure_no_other_active(db, s):
    other = db.query(ClassSession).filter(ClassSession.class_id == s.class_id, ClassSession.status == "active",
                                          ClassSession.id != s.id).first()
    if other:
        raise HTTPException(409, f"Another session of this class is already active ({other.session_date}). Close it first.")


@router.post("/sessions/{session_id}/start")
def start_session(session_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _transition(db, t, session_id, ("scheduled",), "active", "started")
    _ensure_no_other_active(db, s)
    s.status, s.started_at = "active", utcnow()
    audit(db, t.id, "session_start", "session", s.id)
    db.commit()
    return session_out(s)


@router.post("/sessions/{session_id}/reopen")
def reopen_session(session_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _transition(db, t, session_id, ("completed",), "active", "reopened")
    _ensure_no_other_active(db, s)
    s.status, s.ended_at = "active", None
    audit(db, t.id, "session_reopen", "session", s.id)
    db.commit()
    return session_out(s)


@router.post("/sessions/{session_id}/close")
def close_session(session_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _transition(db, t, session_id, ("active",), "completed", "closed")
    s.status, s.ended_at = "completed", utcnow()
    audit(db, t.id, "session_close", "session", s.id)
    db.commit()
    return session_out(s)


@router.post("/sessions/{session_id}/cancel")
def cancel_session(session_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _transition(db, t, session_id, ("scheduled",), "cancelled", "cancelled")
    s.status = "cancelled"
    audit(db, t.id, "session_cancel", "session", s.id)
    db.commit()
    return session_out(s)


@router.get("/sessions/{session_id}")
def session_detail(session_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = get_session(db, t, session_id)
    records = db.query(Attendance).filter_by(session_id=s.id).order_by(Attendance.timestamp).all()
    present_pks = {a.student_pk for a in records}
    absent = [student_out(st) for st in sorted(s.course.students, key=lambda x: x.full_name)
              if st.id not in present_pks]
    ev = dict(db.query(RecognitionEvent.decision, func.count(RecognitionEvent.id))
              .filter_by(session_id=s.id).group_by(RecognitionEvent.decision).all())
    pending = db.query(RecognitionEvent).filter_by(session_id=s.id, review_status="pending").count()
    out = session_out(s, len(records))
    out.update(attendance=[attendance_out(a) for a in records], absent=absent,
               roster_size=len(s.course.students),
               recognition={"unknown": ev.get("unknown", 0), "duplicate": ev.get("duplicate", 0),
                            "accepted": ev.get("accepted", 0), "pending_reviews": pending})
    return out
