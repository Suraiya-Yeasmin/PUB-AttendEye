import json

from sqlalchemy.orm import Session

from ..models import AuditLog


def audit(db: Session, teacher_id: int | None, action: str, entity_type: str,
          entity_id: int | None = None, **detail) -> None:
    """Adds an audit row to the current transaction (caller commits). Never pass biometric data."""
    db.add(AuditLog(teacher_id=teacher_id, action=action, entity_type=entity_type, entity_id=entity_id,
                    detail=json.dumps(detail, default=str) if detail else None))
