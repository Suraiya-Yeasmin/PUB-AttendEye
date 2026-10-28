"""Consent-based, multi-sample face enrollment. Embeddings stay on the server."""
import time

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from .. import config
from ..cv.service import CVUnavailable, face_service
from ..database import get_db
from ..deps import current_teacher
from ..models import FaceTemplate, Student, Teacher, utcnow
from ..schemas import EnrollStartIn
from ..security import encrypt_bytes
from ..services import settings_service
from ..services.audit import audit

router = APIRouter(prefix="/api/enrollment", tags=["enrollment"])

# In-memory drafts: student_pk -> {"samples": [np.ndarray], "teacher": id, "started": ts, "last": ts}
_drafts: dict[int, dict] = {}
MIN_SAMPLE_GAP_S = 0.6
SAMPLE_CONSISTENCY = 0.45  # cosine between a new sample and earlier ones of the same person


def _expire():
    now = time.time()
    for k in [k for k, d in _drafts.items() if now - d["started"] > config.ENROLL_DRAFT_TTL_SECONDS]:
        _drafts.pop(k, None)


@router.post("/start")
def start(body: EnrollStartIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    if not body.consent:
        raise HTTPException(400, "Informed consent is required before biometric enrollment can begin.")
    s = db.get(Student, body.student_pk)
    if not s:
        raise HTTPException(404, "Student not found.")
    if s.status != "active":
        raise HTTPException(409, "Deactivated students cannot be enrolled.")
    if s.template and not body.replace:
        raise HTTPException(409, "This student already has a face template. Choose 'replace' to re-enroll.")
    st = face_service.status()
    if not st["available"]:
        raise HTTPException(503, f"Face recognition service unavailable: {st['error']}")
    _expire()
    _drafts[s.id] = {"samples": [], "teacher": t.id, "started": time.time(), "last": 0.0}
    audit(db, t.id, "enroll_consent_confirmed", "student", s.id)
    db.commit()
    return {"target": config.ENROLL_SAMPLES, "count": 0}


@router.post("/cancel/{student_pk}")
def cancel(student_pk: int, t: Teacher = Depends(current_teacher)):
    _drafts.pop(student_pk, None)
    return {"ok": True}


@router.post("/frame/{student_pk}")
async def frame(student_pk: int, request: Request, t: Teacher = Depends(current_teacher),
                db: Session = Depends(get_db)):
    data = await request.body()
    if not data or len(data) > config.MAX_FRAME_BYTES:
        raise HTTPException(400, "Empty or oversized frame.")
    return await run_in_threadpool(_process, db, student_pk, data, t)


def _process(db: Session, student_pk: int, data: bytes, t: Teacher):
    draft = _drafts.get(student_pk)
    if not draft or draft["teacher"] != t.id:
        raise HTTPException(409, "No enrollment in progress. Confirm consent and start again.")
    if time.time() - draft["started"] > config.ENROLL_DRAFT_TTL_SECONDS:
        _drafts.pop(student_pk, None)
        raise HTTPException(409, "Enrollment timed out. Please start again.")
    s = db.get(Student, student_pk)
    settings = settings_service.get_all(db)
    try:
        img = face_service.decode(data)
        faces = face_service.detect(img)
    except CVUnavailable as e:
        raise HTTPException(503, f"Face recognition service unavailable: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    h, w = img.shape[:2]
    base = {"target": config.ENROLL_SAMPLES, "count": len(draft["samples"]), "frame": {"w": w, "h": h}, "bbox": None}

    def reply(status, message, **kw):
        return {**base, "status": status, "message": message, **kw}

    if not faces:
        return reply("no_face", "No face detected.")
    if len(faces) > 1:
        return reply("multiple_faces", "Multiple faces detected. Please ensure only the intended participant is visible.")
    face = faces[0]
    base["bbox"] = {"x": int(face[0]), "y": int(face[1]), "w": int(face[2]), "h": int(face[3])}
    q = face_service.assess_quality(img, face, settings)
    if not q["ok"]:
        return reply("poor_quality", "Image quality is insufficient. " + " ".join(q["messages"]), quality=q)
    if time.time() - draft["last"] < MIN_SAMPLE_GAP_S:
        return reply("waiting", "Hold still — capturing…", quality=q)
    vec = face_service.embed(img, face)
    if draft["samples"]:
        ref = np.mean(draft["samples"], axis=0)
        ref /= np.linalg.norm(ref)
        if float(ref @ vec) < SAMPLE_CONSISTENCY:
            return reply("inconsistent", "This face differs from the earlier samples. Only one person may be enrolled at a time.", quality=q)
    draft["samples"].append(vec)
    draft["last"] = time.time()
    draft.setdefault("sharp", []).append(q["metrics"]["sharpness"])
    base["count"] = len(draft["samples"])
    if base["count"] < config.ENROLL_SAMPLES:
        return reply("captured", "Sample captured. Slightly vary your head position and keep looking at the camera.", quality=q)

    # --- finalise ----------------------------------------------------------------------------
    mean = np.mean(draft["samples"], axis=0)
    mean = (mean / np.linalg.norm(mean)).astype(np.float32)
    ids, matrix = face_service.gallery(db)
    for pk, row in zip(ids, matrix):
        if pk != student_pk and float(row @ mean) >= settings["accept_threshold"]:
            other = db.get(Student, pk)
            _drafts.pop(student_pk, None)
            return reply("duplicate_face", f"This face closely matches an already enrolled student ({other.student_id}). "
                                           "Enrollment was not saved.", quality=q)
    if s.template:
        db.delete(s.template)
        db.flush()
    db.add(FaceTemplate(student_pk=s.id, embedding_enc=encrypt_bytes(mean.tobytes()),
                        model_name="SFace-2021dec", sample_count=len(draft["samples"]),
                        min_quality_sharpness=min(draft["sharp"]), consent_recorded_at=utcnow(),
                        consent_recorded_by=t.id))
    s.biometric_consent = "granted"
    audit(db, t.id, "enroll_complete", "student", s.id, samples=len(draft["samples"]))
    db.commit()
    face_service.invalidate_gallery()
    _drafts.pop(student_pk, None)
    return reply("completed", "Face enrollment completed successfully.", quality=q)
