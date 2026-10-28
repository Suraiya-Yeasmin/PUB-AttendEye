"""Shared FastAPI dependencies: authentication, authorisation and ownership checks."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import ClassCourse, ClassSession, Teacher, utcnow
from .security import read_token


def current_teacher(request: Request, db: Session = Depends(get_db)) -> Teacher:
    payload = read_token(request.cookies.get(config.SESSION_COOKIE))
    if not payload:
        raise HTTPException(401, "Not authenticated. Please sign in.")
    t = db.get(Teacher, payload["t"])
    if not t or not t.is_active or t.session_epoch != payload["e"]:
        raise HTTPException(401, "Session expired. Please sign in again.")
    return t


def require_admin(teacher: Teacher = Depends(current_teacher)) -> Teacher:
    if teacher.role != "admin":
        raise HTTPException(403, "Administrator permission is required for this action.")
    return teacher


def get_course(db: Session, teacher: Teacher, class_id: int) -> ClassCourse:
    c = db.get(ClassCourse, class_id)
    if not c:
        raise HTTPException(404, "Class not found.")
    if teacher.role != "admin" and c.teacher_id != teacher.id:
        raise HTTPException(403, "You do not have access to this class.")
    return c


def get_session(db: Session, teacher: Teacher, session_id: int) -> ClassSession:
    s = db.get(ClassSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found.")
    get_course(db, teacher, s.class_id)
    return s


def accessible_class_ids(db: Session, teacher: Teacher):
    q = db.query(ClassCourse.id)
    if teacher.role != "admin":
        q = q.filter(ClassCourse.teacher_id == teacher.id)
    return [r[0] for r in q.all()]


def now():
    return utcnow()
