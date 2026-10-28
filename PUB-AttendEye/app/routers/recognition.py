from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from .. import config
from ..cv.service import CVUnavailable, face_service
from ..database import get_db
from ..deps import current_teacher, get_session
from ..models import RecognitionEvent, Teacher
from ..serializers import event_out
from ..services import recognition as rec
from ..services import settings_service
from ..services.attendance import present_count
from ..services.trustscore import DECISION_LABELS, SIMILARITY_EXPLAINER

router = APIRouter(prefix="/api/recognition", tags=["recognition"])


@router.get("/status")
def status(t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    st = face_service.status()
    s = settings_service.get_all(db)
    ids, _ = face_service.gallery(db) if st["available"] else ([], None)
    return {**st, "enrolled_templates": len(ids), "decision_labels": DECISION_LABELS,
            "similarity_explainer": SIMILARITY_EXPLAINER,
            "policy": {k: s[k] for k in ("accept_threshold", "review_threshold", "margin", "confirm_frames")},
            "frame_interval_ms": 700}


@router.post("/frame")
async def recognise_frame(request: Request, session_id: int = Query(...),
                          t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    data = await request.body()
    if not data or len(data) > config.MAX_FRAME_BYTES:
        raise HTTPException(400, "Empty or oversized frame.")
    session = get_session(db, t, session_id)
    if session.status != "active":  # closed / scheduled / cancelled sessions never accept attempts
        raise HTTPException(409, "Session Not Active: attendance attempts are rejected until the session is started.")
    settings = settings_service.get_all(db)
    try:
        return await run_in_threadpool(rec.process_session_frame, db, session, data, settings, t.id)
    except CVUnavailable as e:
        raise HTTPException(503, f"Face recognition service unavailable: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/events")
def events(session_id: int, limit: int = Query(40, le=200), t: Teacher = Depends(current_teacher),
           db: Session = Depends(get_db)):
    s = get_session(db, t, session_id)
    rows = (db.query(RecognitionEvent).filter_by(session_id=s.id).order_by(RecognitionEvent.id.desc())
            .limit(limit).all())
    return {"items": [event_out(e) for e in rows], "verified_total": present_count(db, s.id),
            "session_status": s.status}
