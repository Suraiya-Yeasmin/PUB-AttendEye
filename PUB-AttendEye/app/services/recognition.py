"""Frame-level recognition pipeline plus the session rules that turn a match into a decision."""
import threading
import time
from time import perf_counter

from sqlalchemy.orm import Session

from ..cv.service import face_service
from ..models import Attendance, ClassSession, RecognitionEvent, Student, utcnow
from . import trustscore as ts
from .attendance import DuplicateAttendance, present_count, record_attendance, roster_pks

STREAK_WINDOW_S = 5.0
UNKNOWN_COOLDOWN_S = 20.0
DUPLICATE_COOLDOWN_S = 15.0

_lock = threading.Lock()
_streaks: dict[tuple[int, int], list[float]] = {}
_last_unknown: dict[int, float] = {}
_last_duplicate: dict[tuple[int, int], float] = {}


def _streak_hit(session_id: int, student_pk: int, needed: int) -> bool:
    """Counts consecutive accepted frames for a candidate inside a short time window."""
    now = time.time()
    with _lock:
        hits = [t for t in _streaks.get((session_id, student_pk), []) if now - t <= STREAK_WINDOW_S]
        hits.append(now)
        _streaks[(session_id, student_pk)] = hits
        if len(hits) >= needed:
            _streaks.pop((session_id, student_pk), None)
            return True
        return False


def _cooldown(store: dict, key, seconds: float) -> bool:
    """True if the event should be recorded (cooldown elapsed); updates the timestamp."""
    now = time.time()
    with _lock:
        if now - store.get(key, 0) < seconds:
            return False
        store[key] = now
        return True


def reset_state():
    with _lock:
        _streaks.clear(); _last_unknown.clear(); _last_duplicate.clear()


def _trust_block(sim, runner, quality, det_score, decision, reason, review_required, duplicate) -> dict:
    return {"similarity": None if sim is None else round(sim, 3),
            "runner_up_gap": None if (sim is None or runner is None) else round(sim - runner, 3),
            "quality_ok": quality["ok"], "quality_issues": quality["issues"],
            "quality_messages": quality["messages"], "quality_metrics": quality["metrics"],
            "face_detected": True, "decision": decision, "decision_label": ts.DECISION_LABELS[decision],
            "reason": reason, "review_required": review_required, "duplicate": duplicate}


def analyze_frame(img, settings: dict, gallery):
    """Detection + quality + embedding + gallery match + policy. No database writes, no session rules.
    Used by live attendance, and by the evaluation tool."""
    policy = ts.Policy.from_settings(settings)
    faces = face_service.detect(img)
    out = []
    for face in faces[: settings["max_faces"]]:
        q = face_service.assess_quality(img, face, settings)
        item = {"face": face, "quality": q, "student_pk": None, "similarity": None, "runner_up": None,
                "decision": ts.POOR_QUALITY if not q["ok"] else None, "reason": " ".join(q["messages"]),
                "embedding": None}
        if q["ok"]:
            vec = face_service.embed(img, face)
            pk, sim, runner = face_service.match(vec, gallery)
            decision, reason = ts.decide(sim, runner, policy)
            item.update(student_pk=pk, similarity=sim, runner_up=runner, decision=decision, reason=reason)
        out.append(item)
    return faces, out


def _bbox(face):
    return {"x": int(face[0]), "y": int(face[1]), "w": int(face[2]), "h": int(face[3])}


def process_session_frame(db: Session, session: ClassSession, data: bytes, settings: dict,
                          teacher_id: int) -> dict:
    t0 = perf_counter()
    img = face_service.decode(data)
    h, w = img.shape[:2]
    gallery = face_service.gallery(db)
    faces, analyses = analyze_frame(img, settings, gallery)
    roster = roster_pks(session.course)
    results = []
    for a in analyses:
        face, q = a["face"], a["quality"]
        res = {"bbox": _bbox(face), "state": None, "candidate": None, "attendance_created": False}
        decision, reason, sim, runner = a["decision"], a["reason"], a["similarity"], a["runner_up"]
        student = db.get(Student, a["student_pk"]) if a["student_pk"] else None
        review_required = False
        duplicate = False

        if decision == ts.POOR_QUALITY:
            res["state"] = "poor_quality"

        elif decision == ts.UNKNOWN:
            res["state"] = "unknown"
            if _cooldown(_last_unknown, session.id, UNKNOWN_COOLDOWN_S):
                db.add(RecognitionEvent(session_id=session.id, similarity=sim, runner_up_similarity=runner,
                                        decision=ts.UNKNOWN, reason=reason, face_count=len(faces),
                                        processing_ms=(perf_counter() - t0) * 1000))
                db.commit()

        else:
            # decision is ACCEPTED or NEEDS_REVIEW and a candidate exists
            if decision == ts.ACCEPTED and roster and student.id not in roster:
                decision = ts.NEEDS_REVIEW
                reason = (f"{student.full_name} matched (similarity {sim:.2f}) but is not on this class roster; "
                          "teacher confirmation is required.")
            already = (db.query(Attendance).filter_by(session_id=session.id, student_pk=student.id).first())
            res["candidate"] = {"student_pk": student.id, "student_id": student.student_id,
                                "full_name": student.full_name}
            if decision == ts.ACCEPTED:
                if already:
                    decision, duplicate = ts.DUPLICATE, True
                    reason = f"Already marked present at {already.timestamp.strftime('%H:%M:%S')} UTC; no new record created."
                    res["state"] = "duplicate"
                    if _cooldown(_last_duplicate, (session.id, student.id), DUPLICATE_COOLDOWN_S):
                        db.add(RecognitionEvent(session_id=session.id, student_pk=student.id, similarity=sim,
                                                runner_up_similarity=runner, decision=ts.DUPLICATE, reason=reason,
                                                face_count=len(faces), processing_ms=(perf_counter() - t0) * 1000))
                        db.commit()
                elif not _streak_hit(session.id, student.id, settings["confirm_frames"]):
                    decision = ts.PENDING
                    reason = (f"Candidate match; waiting for {settings['confirm_frames']} consecutive "
                              "agreeing frames before attendance is recorded.")
                    res["state"] = "pending"
                else:
                    ev = RecognitionEvent(session_id=session.id, student_pk=student.id, similarity=sim,
                                          runner_up_similarity=runner, decision=ts.ACCEPTED, reason=reason,
                                          face_count=len(faces), processing_ms=(perf_counter() - t0) * 1000)
                    db.add(ev)
                    db.flush()
                    try:
                        record_attendance(db, session, student, method="face", similarity=sim, event_id=ev.id)
                        db.commit()
                        res["state"], res["attendance_created"] = "verified", True
                    except DuplicateAttendance:
                        db.rollback()
                        decision, duplicate, res["state"] = ts.DUPLICATE, True, "duplicate"
                        reason = "Attendance for this student was recorded a moment ago; no new record created."
            else:  # NEEDS_REVIEW
                review_required = True
                res["state"] = "review"
                if already:
                    reason += " (Student is already marked present, so no review case was opened.)"
                    review_required = False
                else:
                    pending = (db.query(RecognitionEvent).filter_by(
                        session_id=session.id, student_pk=student.id, review_status="pending").first())
                    if not pending:
                        thumb = (face_service.thumbnail(img, face) if settings["store_review_thumbnails"] else None)
                        db.add(RecognitionEvent(session_id=session.id, student_pk=student.id, similarity=sim,
                                                runner_up_similarity=runner, decision=ts.NEEDS_REVIEW,
                                                reason=reason, review_status="pending", face_count=len(faces),
                                                processing_ms=(perf_counter() - t0) * 1000, thumbnail=thumb))
                        db.commit()

        if res["state"] == "unknown" or res["state"] == "poor_quality":
            res["candidate"] = None  # never show an identity for these states
        res["trust"] = _trust_block(sim, runner, q, q["metrics"]["detector_score"], decision, reason,
                                    review_required, duplicate)
        results.append(res)

    return {"frame": {"w": w, "h": h}, "faces": results, "face_count": len(faces),
            "processing_ms": round((perf_counter() - t0) * 1000, 1),
            "session_status": session.status, "verified_total": present_count(db, session.id),
            "message": None if faces else "No face detected."}
