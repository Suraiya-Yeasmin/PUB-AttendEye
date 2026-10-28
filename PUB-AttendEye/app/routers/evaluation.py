"""Measured performance of the recognition pipeline, computed only from recorded, labelled samples."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config
from ..cv.service import CVUnavailable, face_service
from ..database import get_db
from ..deps import accessible_class_ids, current_teacher, require_admin
from ..models import ClassSession, EvaluationSample, RecognitionEvent, Student, Teacher
from ..serializers import iso
from ..services import recognition as rec
from ..services import settings_service
from ..services import trustscore as ts
from ..services.audit import audit
from time import perf_counter

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

METHOD = ("Each sample is a single webcam capture taken through the Evaluation tool. The operator states the "
          "ground truth (which enrolled student is in front of the camera, or 'not enrolled'). The full pipeline "
          "(detection, quality gate, embedding, gallery match, decision policy) runs on the capture and the "
          "decision is stored with the thresholds that were active. Metrics below are counts of those stored "
          "decisions. Session rules (duplicates, rosters) are not applied to evaluation samples.")


@router.post("/sample", status_code=201)
async def add_sample(request: Request, truth: str = Query(..., description="student pk or 'unknown'"),
                     condition: str = Query("", max_length=80), t: Teacher = Depends(current_teacher),
                     db: Session = Depends(get_db)):
    data = await request.body()
    if not data or len(data) > config.MAX_FRAME_BYTES:
        raise HTTPException(400, "Empty or oversized frame.")
    truth_pk = None
    if truth != "unknown":
        if not truth.isdigit() or not db.get(Student, int(truth)):
            raise HTTPException(404, "Ground-truth student not found.")
        truth_pk = int(truth)
        if not db.get(Student, truth_pk).template:
            raise HTTPException(409, "That student has no face template, so they cannot be a genuine sample.")
    settings = settings_service.get_all(db)

    def work():
        t0 = perf_counter()
        img = face_service.decode(data)
        gallery = face_service.gallery(db)
        _, analyses = rec.analyze_frame(img, settings, gallery)
        return analyses, (perf_counter() - t0) * 1000

    try:
        analyses, ms = await run_in_threadpool(work)
    except CVUnavailable as e:
        raise HTTPException(503, f"Face recognition service unavailable: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not analyses:
        raise HTTPException(422, "No face detected; nothing was recorded.")
    if len(analyses) > 1:
        raise HTTPException(422, "Multiple faces detected; evaluation captures must contain exactly one face.")
    a = analyses[0]
    sample = EvaluationSample(teacher_id=t.id, truth_student_pk=truth_pk, predicted_student_pk=a["student_pk"],
                              similarity=a["similarity"], decision=a["decision"],
                              quality_status="ok" if a["quality"]["ok"] else ",".join(a["quality"]["issues"])[:24],
                              processing_ms=ms, condition=condition.strip() or None,
                              accept_threshold=settings["accept_threshold"], review_threshold=settings["review_threshold"])
    db.add(sample)
    db.commit()
    return {"id": sample.id, "decision": a["decision"], "decision_label": ts.DECISION_LABELS[a["decision"]],
            "similarity": None if a["similarity"] is None else round(a["similarity"], 3),
            "reason": a["reason"], "processing_ms": round(ms, 1),
            "outcome": _classify(sample)}


def _classify(s: EvaluationSample) -> str:
    if s.decision == ts.POOR_QUALITY:
        return "unusable_quality"
    if s.truth_student_pk is not None:  # genuine
        if s.decision == ts.ACCEPTED:
            return "correct_match" if s.predicted_student_pk == s.truth_student_pk else "false_accept"
        if s.decision == ts.NEEDS_REVIEW:
            return "sent_to_review"
        return "false_reject"
    # impostor / not enrolled
    if s.decision == ts.ACCEPTED:
        return "false_accept"
    if s.decision == ts.NEEDS_REVIEW:
        return "sent_to_review"
    return "correct_rejection"


def threshold_sweep(genuine, impostor):
    """Similarity-only what-if analysis over the stored samples (no new data, no estimation).
    A sample counts as 'accepted at t' when its best-match similarity >= t. The live policy also applies a
    runner-up margin, so real behaviour can only be stricter than this table."""
    rows = []
    for t in [round(0.30 + 0.05 * i, 2) for i in range(11)]:  # 0.30 .. 0.80
        ok = sum(1 for s in genuine if s.similarity is not None and s.similarity >= t and s.predicted_student_pk == s.truth_student_pk)
        misid = sum(1 for s in genuine if s.similarity is not None and s.similarity >= t and s.predicted_student_pk != s.truth_student_pk)
        imp = sum(1 for s in impostor if s.similarity is not None and s.similarity >= t)
        rows.append({"threshold": t, "genuine_accepted": ok, "genuine_missed": len(genuine) - ok - misid,
                     "misidentified": misid, "impostor_accepted": imp,
                     "false_accepts": misid + imp,
                     "false_accept_rate": round((misid + imp) / (len(genuine) + len(impostor)), 4) if (genuine or impostor) else None,
                     "false_reject_rate": round((len(genuine) - ok - misid) / len(genuine), 4) if genuine else None})
    return rows


@router.get("/summary")
def summary(t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    samples = db.query(EvaluationSample).all()
    n = len(samples)
    counts = {k: 0 for k in ("correct_match", "false_accept", "false_reject", "correct_rejection",
                             "sent_to_review", "unusable_quality")}
    for s in samples:
        counts[_classify(s)] += 1
    genuine = [s for s in samples if s.truth_student_pk is not None and s.decision != ts.POOR_QUALITY]
    impostor = [s for s in samples if s.truth_student_pk is None and s.decision != ts.POOR_QUALITY]
    usable = len(genuine) + len(impostor)
    times = [s.processing_ms for s in samples if s.processing_ms is not None]
    thresholds = {(s.accept_threshold, s.review_threshold) for s in samples}
    conditions: dict[str, int] = {}
    for s in samples:
        conditions[s.condition or "unspecified"] = conditions.get(s.condition or "unspecified", 0) + 1
    # live operational counters (real events, not labelled -> reported separately and never as accuracy)
    mine = (db.query(RecognitionEvent).join(ClassSession, ClassSession.id == RecognitionEvent.session_id)
            .filter(ClassSession.class_id.in_(accessible_class_ids(db, t) or [0])))  # only this teacher's classes
    ev = dict(mine.with_entities(RecognitionEvent.decision, func.count(RecognitionEvent.id))
              .group_by(RecognitionEvent.decision).all())
    live_total = sum(ev.get(k, 0) for k in ("accepted", "needs_review", "unknown"))
    live_ms = mine.with_entities(func.avg(RecognitionEvent.processing_ms)).scalar()
    evaluated = n > 0
    return {
        "evaluated": evaluated,
        "method": METHOD,
        "samples": n, "genuine_samples": len(genuine), "impostor_samples": len(impostor), **counts,
        "false_accept_rate": round(counts["false_accept"] / usable, 4) if usable else None,
        "false_reject_rate": round(counts["false_reject"] / len(genuine), 4) if genuine else None,
        "review_rate": round(counts["sent_to_review"] / usable, 4) if usable else None,
        "avg_processing_ms": round(sum(times) / len(times), 1) if times else None,
        "thresholds_used": [{"accept": a, "review": r} for a, r in sorted(thresholds)],
        "thresholds_vary": len(thresholds) > 1,
        "conditions": conditions,
        "threshold_sweep": threshold_sweep(genuine, impostor) if usable else [],
        "sweep_note": ("Computed from the stored similarity of each labelled sample. It ignores the runner-up margin and "
                       "the review band, so it is a similarity-only what-if for choosing the accept threshold. "
                       "It is only as reliable as the number and variety of your samples."),
        "small_sample_warning": evaluated and (len(genuine) < 30 or len(impostor) < 30),
        "live": {"events": live_total, "accepted": ev.get("accepted", 0), "needs_review": ev.get("needs_review", 0),
                 "unknown": ev.get("unknown", 0), "duplicates_prevented": ev.get("duplicate", 0),
                 "live_review_rate": round(ev.get("needs_review", 0) / live_total, 4) if live_total else None,
                 "avg_processing_ms": round(live_ms, 1) if live_ms else None},
    }


@router.get("/samples")
def list_samples(limit: int = Query(30, le=200), t: Teacher = Depends(current_teacher),
                 db: Session = Depends(get_db)):
    rows = db.query(EvaluationSample).order_by(EvaluationSample.id.desc()).limit(limit).all()
    return {"items": [{"id": s.id, "timestamp": iso(s.timestamp), "decision": s.decision,
                       "decision_label": ts.DECISION_LABELS.get(s.decision), "outcome": _classify(s),
                       "truth": "Not enrolled" if s.truth_student_pk is None else "Enrolled student",
                       "similarity": None if s.similarity is None else round(s.similarity, 3),
                       "processing_ms": None if s.processing_ms is None else round(s.processing_ms, 1),
                       "condition": s.condition} for s in rows]}


@router.delete("/samples")
def reset(admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    n = db.query(EvaluationSample).delete()
    audit(db, admin.id, "evaluation_reset", "evaluation", None, deleted=n)
    db.commit()
    return {"deleted": n}
