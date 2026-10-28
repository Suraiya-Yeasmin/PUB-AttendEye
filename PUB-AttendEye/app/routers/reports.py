import csv
import io
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_class_ids, current_teacher, get_course, get_session
from ..models import Attendance, ClassCourse, ClassSession, RecognitionEvent, Student, Teacher, class_students
from ..services.audit import audit
from .attendance import history_query

router = APIRouter(prefix="/api/reports", tags=["reports"])
COUNTED = ("active", "completed")  # scheduled / cancelled sessions carry no attendance information
DEFINITIONS = {
    "present": "Confirmed attendance records with status present or late (face, teacher-confirmed face, or manual).",
    "absent": "Roster students with no attendance record and no excused record. Students whose face match is still "
              "waiting for teacher review are counted separately as 'pending review', not as absent.",
    "pending_review": "Open review cases for a candidate who has no attendance record yet. They may become present "
                      "when the teacher confirms them.",
    "percentage": "(present + late) / roster size x 100. Excused records are not in the numerator. Pending-review "
                  "cases are not counted as present. Sessions without a roster have no percentage.",
}


def csv_safe(v):
    """Neutralise spreadsheet formula injection (=, +, -, @, tab, CR at the start of a cell)."""
    if v is None:
        return ""
    s = str(v)
    return "'" + s if s and s[0] in "=+-@\t\r" else s


def _pct(present, total):
    return round(100.0 * present / total, 1) if total else None


def _sessions(db, t, class_id, date_from, date_to):
    q = db.query(ClassSession).join(ClassCourse).filter(
        ClassSession.status.in_(COUNTED), ClassSession.class_id.in_(accessible_class_ids(db, t) or [0]))
    if class_id:
        q = q.filter(ClassSession.class_id == class_id)
    from datetime import datetime
    try:
        if date_from:
            q = q.filter(ClassSession.session_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        if date_to:
            q = q.filter(ClassSession.session_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
    except ValueError:
        raise HTTPException(400, "Dates must use YYYY-MM-DD.")
    return q.order_by(ClassSession.session_date, ClassSession.start_time).all()


def _session_rows(db, sessions):
    ids = [s.id for s in sessions] or [0]
    present = dict(db.query(Attendance.session_id, func.count(Attendance.id))
                   .filter(Attendance.session_id.in_(ids), Attendance.status.in_(["present", "late"]))
                   .group_by(Attendance.session_id).all())
    excused = dict(db.query(Attendance.session_id, func.count(Attendance.id))
                   .filter(Attendance.session_id.in_(ids), Attendance.status == "excused")
                   .group_by(Attendance.session_id).all())
    # distinct candidates with an open review case and no attendance row yet
    pending: dict[int, int] = {}
    for sid, spk in (db.query(RecognitionEvent.session_id, RecognitionEvent.student_pk)
                     .filter(RecognitionEvent.session_id.in_(ids), RecognitionEvent.review_status == "pending",
                             RecognitionEvent.student_pk.isnot(None)).distinct().all()):
        has = db.query(Attendance.id).filter_by(session_id=sid, student_pk=spk).first()
        if not has:
            pending[sid] = pending.get(sid, 0) + 1
    rows = []
    for s in sessions:
        roster = len(s.course.students)
        p, ex = present.get(s.id, 0), excused.get(s.id, 0)
        pr = pending.get(s.id, 0)
        rows.append({"session_id": s.id, "pending_review": pr, "class_id": s.class_id, "course_code": s.course.code,
                     "course_name": s.course.name, "section": s.course.section,
                     "session_date": s.session_date.isoformat(), "status": s.status, "roster_size": roster,
                     "present": p, "excused": ex, "absent": max(roster - p - ex - pr, 0) if roster else None,
                     "percentage": _pct(p, roster)})
    return rows


@router.get("/summary")
def summary(class_id: int | None = None, date_from: str = "", date_to: str = "",
            t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    if class_id:
        get_course(db, t, class_id)
    rows = _session_rows(db, _sessions(db, t, class_id, date_from, date_to))
    by_class = defaultdict(list)
    for r in rows:
        by_class[r["class_id"]].append(r)
    classes = []
    for cid, rs in by_class.items():
        pcts = [r["percentage"] for r in rs if r["percentage"] is not None]
        classes.append({"class_id": cid, "course_code": rs[0]["course_code"], "course_name": rs[0]["course_name"],
                        "section": rs[0]["section"], "sessions": len(rs), "roster_size": rs[0]["roster_size"],
                        "average_percentage": round(sum(pcts) / len(pcts), 1) if pcts else None})
    all_p = [r["percentage"] for r in rows if r["percentage"] is not None]
    return {"sessions": rows, "classes": classes,
            "definitions": DEFINITIONS,
            "totals": {"sessions": len(rows), "present": sum(r["present"] for r in rows),
                       "pending_review": sum(r["pending_review"] for r in rows),
                       "average_percentage": round(sum(all_p) / len(all_p), 1) if all_p else None}}


def _student_rows(db, course: ClassCourse, sessions):
    ids = [s.id for s in sessions]
    recs = defaultdict(dict)
    if ids:
        for a in db.query(Attendance).filter(Attendance.session_id.in_(ids)).all():
            recs[a.student_pk][a.session_id] = a.status
    rows = []
    for st in sorted(course.students, key=lambda x: x.full_name):
        got = recs.get(st.id, {})
        attended = sum(1 for v in got.values() if v in ("present", "late"))
        excused = sum(1 for v in got.values() if v == "excused")
        total = len(ids)
        rows.append({"student_pk": st.id, "student_id": st.student_id, "full_name": st.full_name,
                     "sessions": total, "present": attended, "excused": excused,
                     "absent": max(total - attended - excused, 0), "percentage": _pct(attended, total)})
    return rows


@router.get("/class/{class_id}/students")
def class_students_report(class_id: int, date_from: str = "", date_to: str = "",
                          t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    c = get_course(db, t, class_id)
    sessions = _sessions(db, t, class_id, date_from, date_to)
    return {"class": {"id": c.id, "code": c.code, "name": c.name, "section": c.section},
            "sessions": len(sessions), "students": _student_rows(db, c, sessions)}


@router.get("/student/{student_pk}")
def student_history(student_pk: int, class_id: int | None = None, date_from: str = "", date_to: str = "",
                    t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    st = db.get(Student, student_pk)
    if not st:
        raise HTTPException(404, "Student not found.")
    sessions = [s for s in _sessions(db, t, class_id, date_from, date_to)
                if any(x.id == st.id for x in s.course.students)]
    recs = {a.session_id: a for a in db.query(Attendance).filter(
        Attendance.student_pk == st.id, Attendance.session_id.in_([s.id for s in sessions] or [0])).all()}
    items = []
    for s in sessions:
        a = recs.get(s.id)
        items.append({"session_id": s.id, "course_code": s.course.code, "section": s.course.section,
                      "session_date": s.session_date.isoformat(), "status": a.status if a else "absent",
                      "method": a.method if a else None})
    attended = sum(1 for i in items if i["status"] in ("present", "late"))
    return {"student": {"id": st.id, "student_id": st.student_id, "full_name": st.full_name},
            "items": items, "sessions": len(items), "present": attended,
            "percentage": _pct(attended, len(items))}


def _csv(filename: str, header: list[str], rows: list[list]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(c) for c in r])
    # utf-8-sig so Excel on Windows opens non-ASCII names correctly
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Row-Count": str(len(rows)), "Cache-Control": "no-store"})


@router.get("/export")
def export(kind: str = Query(..., pattern="^(session|class_students|sessions|history)$"),
           session_id: int | None = None, class_id: int | None = None, date_from: str = "", date_to: str = "",
           q: str = "", status: str = "", method: str = "",
           t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    if kind == "session":
        if not session_id:
            raise HTTPException(422, "session_id is required.")
        s = get_session(db, t, session_id)
        recs = {a.student_pk: a for a in db.query(Attendance).filter_by(session_id=s.id).all()}
        pending_pks = {e.student_pk for e in db.query(RecognitionEvent).filter_by(
            session_id=s.id, review_status="pending") if e.student_pk}
        students = {st.id: st for st in s.course.students}
        for pk, a in recs.items():  # include non-roster attendees too
            students.setdefault(pk, a.student)
        rows = []
        for st in sorted(students.values(), key=lambda x: x.student_id):
            a = recs.get(st.id)
            rows.append([st.student_id, st.full_name, st.department, st.section,
                         a.status if a else ("pending_review" if st.id in pending_pks else "absent"), a.timestamp.isoformat(timespec="seconds") + "Z" if a else "",
                         a.method if a else "", a.review_status if a else ""])
        audit(db, t.id, "export_session", "session", s.id, rows=len(rows)); db.commit()
        return _csv(f"attendance_{s.course.code}_{s.session_date}.csv".replace(" ", "_"),
                    ["Student ID", "Name", "Department", "Section", "Status", "Timestamp (UTC)", "Method",
                     "Review status"], rows)
    if kind == "class_students":
        if not class_id:
            raise HTTPException(422, "class_id is required.")
        c = get_course(db, t, class_id)
        sessions = _sessions(db, t, class_id, date_from, date_to)
        rows = [[r["student_id"], r["full_name"], r["sessions"], r["present"], r["excused"], r["absent"],
                 "" if r["percentage"] is None else r["percentage"]] for r in _student_rows(db, c, sessions)]
        audit(db, t.id, "export_class_students", "class", c.id, rows=len(rows)); db.commit()
        return _csv(f"student_attendance_{c.code}_{c.section}.csv".replace(" ", "_"),
                    ["Student ID", "Name", "Sessions", "Present", "Excused", "Pending review", "Absent", "Attendance %"], rows)
    if kind == "sessions":
        rs = _session_rows(db, _sessions(db, t, class_id, date_from, date_to))
        rows = [[r["session_date"], r["course_code"], r["course_name"], r["section"], r["status"], r["roster_size"],
                 r["present"], r["excused"], r["pending_review"], "" if r["absent"] is None else r["absent"],
                 "" if r["percentage"] is None else r["percentage"]] for r in rs]
        audit(db, t.id, "export_sessions", "report", None, rows=len(rows)); db.commit()
        return _csv("session_summary.csv", ["Date", "Course code", "Course", "Section", "Status", "Roster",
                                           "Present", "Excused", "Pending review", "Absent", "Attendance %"], rows)
    recs = (history_query(db, t, class_id=class_id, session_id=session_id, q=q, status=status, method=method,
                          date_from=date_from, date_to=date_to).order_by(Attendance.timestamp).all())
    rows = [[a.student.student_id, a.student.full_name, a.session.course.code, a.session.session_date.isoformat(),
             a.timestamp.isoformat(timespec="seconds") + "Z", a.method, a.status, a.review_status,
             "yes" if a.corrected else "no"] for a in recs]
    audit(db, t.id, "export_history", "report", None, rows=len(rows)); db.commit()
    return _csv("attendance_history.csv", ["Student ID", "Name", "Course", "Session date", "Timestamp (UTC)",
                                           "Method", "Status", "Review status", "Corrected"], rows)
