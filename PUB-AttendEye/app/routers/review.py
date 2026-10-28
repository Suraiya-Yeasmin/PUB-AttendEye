from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_class_ids, current_teacher, get_session
from ..models import ClassSession, RecognitionEvent, ReviewEvent, Teacher, utcnow
from ..schemas import ReviewDecisionIn
from ..serializers import event_out, iso
from ..services.attendance import DuplicateAttendance, record_attendance
from ..services.audit import audit

router = APIRouter(prefix="/api/review", tags=["review"])

QUALITY_LABEL = {"ok": "Passed quality checks"}


def _case(e: RecognitionEvent) -> dict:
    out = event_out(e)
    c = e.session.course
    out.update(course_code=c.code, course_name=c.name, section=c.section,
               session_date=e.session.session_date.isoformat(), session_status=e.session.status,
               quality_label=QUALITY_LABEL.get(e.quality_status, e.quality_status))
    return out


@router.get("")
def queue(status: str = "pending", session_id: int | None = None, limit: int = Query(100, le=300),
          t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    q = (db.query(RecognitionEvent).join(ClassSession, ClassSession.id == RecognitionEvent.session_id)
         .filter(ClassSession.class_id.in_(accessible_class_ids(db, t) or [0])))
    if status == "pending":
        q = q.filter(RecognitionEvent.review_status == "pending")
    elif status == "decided":
        q = q.filter(RecognitionEvent.review_status.in_(["confirmed", "rejected", "unknown"]))
    else:
        q = q.filter(RecognitionEvent.review_status != "none")
    if session_id:
        q = q.filter(RecognitionEvent.session_id == session_id)
    rows = q.order_by(RecognitionEvent.id.desc()).limit(limit).all()
    pending = (db.query(RecognitionEvent).join(ClassSession, ClassSession.id == RecognitionEvent.session_id)
               .filter(ClassSession.class_id.in_(accessible_class_ids(db, t) or [0]),
                       RecognitionEvent.review_status == "pending").count())
    return {"items": [_case(e) for e in rows], "pending_total": pending}


def _event(db, t, event_id) -> RecognitionEvent:
    e = db.get(RecognitionEvent, event_id)
    if not e:
        raise HTTPException(404, "Review case not found.")
    get_session(db, t, e.session_id)
    return e


@router.get("/{event_id}/thumbnail")
def thumbnail(event_id: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    e = _event(db, t, event_id)
    if not e.thumbnail:
        raise HTTPException(404, "No thumbnail is stored for this case.")
    return Response(e.thumbnail, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{event_id}/decision")
def decide(event_id: int, body: ReviewDecisionIn, t: Teacher = Depends(current_teacher),
           db: Session = Depends(get_db)):
    e = _event(db, t, event_id)
    if e.review_status != "pending":
        raise HTTPException(409, f"This case was already decided ({e.review_status}).")
    outcome = ""
    if body.action == "keep_pending":
        outcome = "Left pending for later."
    elif body.action == "reject":
        e.review_status, outcome = "rejected", "Candidate rejected; no attendance recorded."
    elif body.action == "unknown":
        e.review_status, outcome = "unknown", "Marked as unknown identity; no attendance recorded."
    else:  # confirm: revalidate session, student and duplicate constraint before creating attendance
        if not e.student:
            raise HTTPException(409, "This case has no candidate student to confirm.")
        session = e.session
        if session.status != "active":
            raise HTTPException(409, "The session is not active, so attendance cannot be created. "
                                     "Reopen the session from Classes & Sessions to confirm this case.")
        if e.student.status != "active":
            raise HTTPException(409, "The candidate's student record is deactivated.")
        try:
            record_attendance(db, session, e.student, method="face_review", teacher_id=t.id,
                              similarity=e.similarity, event_id=e.id, review_status="teacher_confirmed")
            outcome = f"Confirmed: attendance recorded for {e.student.full_name}."
        except DuplicateAttendance:
            outcome = "Confirmed, but the student was already marked present; no new record created."
        e.review_status = "confirmed"
    if body.action != "keep_pending":
        e.reviewed_by, e.reviewed_at = t.id, utcnow()
        e.thumbnail = None  # face thumbnail is deleted as soon as the teacher has decided
    db.add(ReviewEvent(recognition_event_id=e.id, teacher_id=t.id, action=body.action, outcome=outcome,
                       note=body.note))
    audit(db, t.id, f"review_{body.action}", "recognition_event", e.id, outcome=outcome)
    db.commit()
    return {"case": _case(e), "message": outcome}
