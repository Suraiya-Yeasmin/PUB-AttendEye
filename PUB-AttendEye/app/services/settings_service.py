"""Typed, validated application settings stored in the `settings` table."""
from sqlalchemy.orm import Session

from ..models import Setting, utcnow

# protected=True -> only administrators may change the value.
DEFINITIONS: dict[str, dict] = {
    "accept_threshold": dict(type=float, default=0.50, min=0.20, max=0.95, protected=True, group="policy",
                             label="Automatic-accept similarity",
                             help="Cosine similarity at or above which a match may be accepted automatically."),
    "review_threshold": dict(type=float, default=0.363, min=0.10, max=0.90, protected=True, group="policy",
                             label="Review similarity",
                             help="Below this value the face is treated as an unknown identity. 0.363 is the "
                                  "SFace reference operating point published by OpenCV (LFW benchmark)."),
    "margin": dict(type=float, default=0.05, min=0.0, max=0.5, protected=True, group="policy",
                   label="Required margin over runner-up",
                   help="Minimum similarity gap between the best and second-best enrolled student."),
    "confirm_frames": dict(type=int, default=2, min=1, max=6, protected=True, group="policy",
                           label="Consecutive confirmations",
                           help="Number of consecutive frames (within 5 s) that must agree before attendance is created."),
    "min_face_px": dict(type=int, default=80, min=40, max=400, protected=True, group="quality",
                        label="Minimum face width (px)", help="Faces smaller than this are rejected as poor quality."),
    "min_sharpness": dict(type=float, default=30.0, min=0.0, max=500.0, protected=True, group="quality",
                          label="Minimum sharpness", help="Variance of the Laplacian on the aligned face crop."),
    "min_brightness": dict(type=int, default=45, min=0, max=200, protected=True, group="quality",
                           label="Minimum brightness", help="Mean grey level of the aligned face crop (0-255)."),
    "max_brightness": dict(type=int, default=220, min=100, max=255, protected=True, group="quality",
                           label="Maximum brightness", help="Rejects over-exposed faces."),
    "max_yaw": dict(type=float, default=0.40, min=0.1, max=1.0, protected=True, group="quality",
                    label="Maximum head turn", help="Nose offset relative to eye distance; larger means turned away."),
    "max_faces": dict(type=int, default=5, min=1, max=10, protected=True, group="quality",
                      label="Max faces per frame", help="Faces beyond this count (smallest first) are ignored."),
    "store_review_thumbnails": dict(type=bool, default=True, min=None, max=None, protected=True, group="privacy",
                                    label="Keep face thumbnail while a review is pending",
                                    help="Lets the teacher see who needs review. Deleted when the review is decided."),
    "event_retention_days": dict(type=int, default=180, min=7, max=3650, protected=True, group="privacy",
                                 label="Recognition-event retention (days)",
                                 help="Recognition events and evaluation samples older than this are purged."),
    "default_session_start": dict(type=str, default="09:00", min=None, max=None, protected=False, group="session",
                                  label="Default session start (HH:MM)", help="Pre-fills the Create Session form."),
    "default_session_minutes": dict(type=int, default=90, min=10, max=480, protected=False, group="session",
                                    label="Default session length (minutes)", help="Pre-fills the end time."),
}


def _coerce(key: str, raw):
    d = DEFINITIONS[key]
    t = d["type"]
    if t is bool:
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(raw)
    if t is str:
        s = str(raw).strip()
        import re
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s):
            raise ValueError("must be a time in HH:MM format")
        return s
    try:
        v = t(raw)
    except (TypeError, ValueError):
        raise ValueError("must be a number")
    if d["min"] is not None and v < d["min"]:
        raise ValueError(f"must be at least {d['min']}")
    if d["max"] is not None and v > d["max"]:
        raise ValueError(f"must be at most {d['max']}")
    return v


def get_all(db: Session) -> dict:
    stored = {s.key: s.value for s in db.query(Setting).all()}
    out = {}
    for key, d in DEFINITIONS.items():
        try:
            out[key] = _coerce(key, stored[key]) if key in stored else d["default"]
        except ValueError:
            out[key] = d["default"]
    return out


def validate_update(values: dict) -> dict:
    """Returns coerced values or raises ValueError({key: message}) aggregated."""
    errors, clean = {}, {}
    for k, v in values.items():
        if k not in DEFINITIONS:
            errors[k] = "unknown setting"
            continue
        try:
            clean[k] = _coerce(k, v)
        except ValueError as e:
            errors[k] = str(e)
    return clean, errors


def cross_check(merged: dict) -> str | None:
    if merged["review_threshold"] >= merged["accept_threshold"]:
        return "The review similarity must be lower than the automatic-accept similarity."
    if merged["min_brightness"] >= merged["max_brightness"]:
        return "Minimum brightness must be lower than maximum brightness."
    return None


def save(db: Session, clean: dict, teacher_id: int):
    for k, v in clean.items():
        row = db.get(Setting, k)
        val = ("1" if v else "0") if isinstance(v, bool) else str(v)
        if row:
            row.value, row.updated_at, row.updated_by = val, utcnow(), teacher_id
        else:
            db.add(Setting(key=k, value=val, updated_at=utcnow(), updated_by=teacher_id))
