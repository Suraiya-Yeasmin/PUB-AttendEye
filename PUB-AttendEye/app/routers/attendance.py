from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_class_ids, current_teacher, get_session
from ..models import Attendance, AuditLog, ClassCourse, ClassSession, Student, Teacher
from ..schemas import CorrectionIn, ManualAttendanceIn, RemovalIn
from ..serializers import attendance_out, iso
from ..services.attendance import DuplicateAttendance, record_attendance, roster_pks
from ..services.audit import audit

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

SORTS = {"timestamp": Attendance.timestamp, "student_id": Student.student_id, "student_name": Student.full_name,
         "course": ClassCourse.code, "session_date": ClassSession.session_date, "status": Attendance.status,
         "method": Attendance.method}


def history_query(db: Session, t: Teacher, *, class_id=None, session_id=None, q="", status="", method="",
                  date_from="", date_to=""):
    """Shared by the history page, reports and CSV export so all three always agree."""
    query = (db.query(Attendance).join(Student, Student.id == Attendance.student_pk)
             .join(ClassSession, ClassSession.id == Attendance.session_id)
             .join(ClassCourse, ClassCourse.id == ClassSession.class_id)
             .filter(ClassSession.class_id.in_(accessible_class_ids(db, t) or [0])))
    if class_id:
        query = query.filter(ClassSession.class_id == class_id)
    if session_id:
        query = query.filter(Attendance.session_id == session_id)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Student.student_id.ilike(like), Student.full_name.ilike(like)))
    if status:
        query = query.filter(Attendance.status == status)
    if method:
        query = query.filter(Attendance.method == method)
    try:
        if date_from:
            query = query.filter(ClassSession.session_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        if date_to:
            query = query.filter(ClassSession.session_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
    except ValueError:
        raise HTTPException(400, "Dates must use YYYY-MM-DD.")
    return query


@router.get("")
def list_attendance(class_id: int | None = None, session_id: int | None = None, q: str = "", status: str = "",
                    method: str = "", date_from: str = "", date_to: str = "", sort: str = "timestamp",
                    direction: str = "desc", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                    t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    query = history_query(db, t, class_id=class_id, session_id=session_id, q=q, status=status, method=method,
                          date_from=date_from, date_to=date_to)
    total = query.count()
    col = SORTS.get(sort, Attendance.timestamp)
    query = query.order_by(desc(col) if direction == "desc" else asc(col), Attendance.id)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [attendance_out(a) for a in rows], "total": total, "page": page, "page_size": page_size}


def _get(db, t, att_id) -> Attendance:
    a = db.get(Attendance, att_id)
    if not a:
        raise HTTPException(404, "Attendance record not found.")
    get_session(db, t, a.session_id)  # authorisation
    return a


@router.get("/{att_id}")
def detail(att_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    a = _get(db, t, att_id)
    trail = (db.query(AuditLog, Teacher.full_name).outerjoin(Teacher, Teacher.id == AuditLog.teacher_id)
             .filter(AuditLog.entity_type == "attendance", AuditLog.entity_id == a.id)
             .order_by(AuditLog.id).all())
    out = attendance_out(a)
    out["audit"] = [{"timestamp": iso(l.timestamp), "action": l.action, "by": name, "detail": l.detail}
                    for l, name in trail]
    return out


@router.put("/{att_id}")
def correct(att_id: int, body: CorrectionIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    a = _get(db, t, att_id)
    before = a.status
    a.status, a.corrected, a.note = body.status, True, body.note
    audit(db, t.id, "attendance_correct", "attendance", a.id, before=before, after=body.status, note=body.note)
    db.commit()
    return attendance_out(a)


@router.post("/{att_id}/remove")
def remove(att_id: int, body: RemovalIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    """Removes a record (student becomes absent). The audit entry keeps a snapshot of what was removed."""
    a = _get(db, t, att_id)
    audit(db, t.id, "attendance_remove", "attendance", a.id, student_id=a.student.student_id,
          session_id=a.session_id, status=a.status, method=a.method, reason=body.reason)
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.post("/manual", status_code=201)
def manual(body: ManualAttendanceIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    """Alternative attendance workflow (no biometrics): the teacher marks a student directly."""
    s = get_session(db, t, body.session_id)
    st = db.get(Student, body.student_pk)
    if not st:
        raise HTTPException(404, "Student not found.")
    roster = roster_pks(s.course)
    if roster and st.id not in roster:
        raise HTTPException(409, "This student is not on the class roster.")
    try:
        a = record_attendance(db, s, st, method="manual", teacher_id=t.id, status=body.status, note=body.note)
    except DuplicateAttendance:
        raise HTTPException(409, f"{st.full_name} already has an attendance record for this session.")
    audit(db, t.id, "attendance_manual", "attendance", a.id, student_id=st.student_id, status=body.status)
    db.commit()
    return attendance_out(a)
