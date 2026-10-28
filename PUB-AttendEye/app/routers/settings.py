from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..cv.service import face_service
from ..database import get_db
from ..deps import current_teacher, require_admin
from ..models import AuditLog, EvaluationSample, FaceTemplate, RecognitionEvent, Student, Teacher, utcnow
from ..schemas import PurgeIn, SettingsIn
from ..services import settings_service as ss
from ..services.audit import audit

router = APIRouter(prefix="/api/settings", tags=["settings"])

THRESHOLD_LIMITS = (
    "Thresholds trade false accepts against false rejects: raising the accept similarity makes wrong "
    "acceptances rarer but sends more genuine students to review; lowering it does the opposite. The defaults "
    "are generic operating points for the SFace model, not values measured in your classroom. Lighting, "
    "camera, ageing, glasses and masks all shift the distribution. Re-tune with the System Evaluation page "
    "and keep the teacher in the loop for uncertain cases. No threshold makes face recognition error-free."
)


@router.get("")
def get_settings(t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    vals = ss.get_all(db)
    defs = {k: {"label": d["label"], "help": d["help"], "type": {float: "number", int: "integer", bool: "boolean",
                                                                  str: "time"}[d["type"]],
               "min": d["min"], "max": d["max"], "protected": d["protected"], "group": d["group"],
               "default": d["default"]} for k, d in ss.DEFINITIONS.items()}
    return {"values": vals, "definitions": defs, "can_edit_protected": t.role == "admin",
            "threshold_limitations": THRESHOLD_LIMITS,
            "app": {"name": config.APP_NAME, "version": config.APP_VERSION, "tagline": config.TAGLINE,
                    "models": config.MODEL_INFO, "cv": face_service.status(),
                    "database": "SQLite (local file)", "notice": "Prototype: not security- or privacy-audited; "
                                                               "do not describe it as production-ready."}}


@router.put("")
def update_settings(body: SettingsIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    clean, errors = ss.validate_update(body.values)
    if errors:
        raise HTTPException(422, {"message": "Some settings are invalid.", "fields": errors})
    protected = [k for k in clean if ss.DEFINITIONS[k]["protected"]]
    if protected and t.role != "admin":
        raise HTTPException(403, f"Only an administrator can change: {', '.join(protected)}.")
    merged = {**ss.get_all(db), **clean}
    problem = ss.cross_check(merged)
    if problem:
        raise HTTPException(422, {"message": problem, "fields": {}})
    before = ss.get_all(db)
    ss.save(db, clean, t.id)
    audit(db, t.id, "settings_update", "settings", None, changes={k: [before[k], v] for k, v in clean.items()
                                                                  if before[k] != v})
    db.commit()
    return {"values": ss.get_all(db)}


@router.post("/purge-biometrics")
def purge_biometrics(body: PurgeIn, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    if body.confirm != "DELETE ALL TEMPLATES":
        raise HTTPException(422, "Type DELETE ALL TEMPLATES to confirm.")
    pks = [r[0] for r in db.query(FaceTemplate.student_pk).all()]
    for s in db.query(Student).filter(Student.id.in_(pks or [0])).all():
        s.biometric_consent = "withdrawn"
    n = db.query(FaceTemplate).delete()
    db.query(RecognitionEvent).update({RecognitionEvent.thumbnail: None})
    audit(db, admin.id, "biometric_purge_all", "settings", None, deleted=n)
    db.commit()
    face_service.invalidate_gallery()
    return {"deleted": n}


def apply_retention(db: Session) -> dict:
    days = ss.get_all(db)["event_retention_days"]
    cutoff = utcnow() - timedelta(days=days)
    ev = db.query(RecognitionEvent).filter(RecognitionEvent.timestamp < cutoff,
                                           RecognitionEvent.review_status != "pending").delete()
    smp = db.query(EvaluationSample).filter(EvaluationSample.timestamp < cutoff).delete()
    db.commit()
    return {"recognition_events_deleted": ev, "evaluation_samples_deleted": smp, "retention_days": days}


@router.post("/apply-retention")
def retention(admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    out = apply_retention(db)
    audit(db, admin.id, "retention_applied", "settings", None, **out)
    db.commit()
    return out
