from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import current_teacher, require_admin
from ..models import Teacher, utcnow
from ..schemas import LoginIn, PasswordIn, ProfileIn, TeacherCreateIn
from ..security import DUMMY_HASH, hash_password, make_token, verify_password
from ..serializers import teacher_out
from ..services.audit import audit
from ..services.demo import ensure_demo, real_teacher_exists

router = APIRouter(prefix="/api", tags=["auth"])


_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _require_local(request: Request, what: str):
    """Self-service sign-up and the demo account are for the computer that runs the app, never the network."""
    if (request.client.host if request.client else "") not in _LOCAL_HOSTS:
        raise HTTPException(403, f"{what} is only available on the computer that runs PUB AttendEye.")


def _reserved(username: str) -> bool:
    return username.strip().lower() == config.DEMO_USERNAME


def _start_session(response: Response, t: Teacher):
    response.set_cookie(config.SESSION_COOKIE, make_token(t.id, t.session_epoch), httponly=True,
                        samesite="strict", max_age=config.SESSION_HOURS * 3600, path="/")


@router.get("/setup/status")
def setup_status(db: Session = Depends(get_db)):
    """True until the first real administrator exists (the demo account does not count)."""
    return {"needs_setup": not real_teacher_exists(db)}


@router.get("/auth/options")
def auth_options(request: Request, db: Session = Depends(get_db)):
    local = (request.client.host if request.client else "") in _LOCAL_HOSTS
    needs = not real_teacher_exists(db)
    return {"needs_setup": needs, "signup_enabled": config.ALLOW_SIGNUP and local and not needs,
            "demo_enabled": config.ENABLE_DEMO and local}


@router.post("/auth/register", status_code=201)
def register(body: TeacherCreateIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Self-service teacher account (never an administrator). Local computer only; can be switched off with
    ATTENDEYE_ALLOW_SIGNUP=0."""
    _require_local(request, "Creating an account")
    if not config.ALLOW_SIGNUP:
        raise HTTPException(403, "Self-service sign-up is turned off. Ask an administrator to create your account.")
    if not real_teacher_exists(db):
        raise HTTPException(409, "Create the administrator account first.")
    uname = body.username.lower()
    if _reserved(uname):
        raise HTTPException(409, "That username is reserved. Please choose another.")
    if db.query(Teacher).filter((Teacher.username == uname) | (Teacher.email == body.email)).first():
        raise HTTPException(409, "Username or email already exists.")
    t = Teacher(username=uname, email=body.email, full_name=body.full_name, role="teacher",
                password_hash=hash_password(body.password))
    db.add(t)
    db.flush()
    audit(db, t.id, "self_register", "teacher", t.id)
    db.commit()
    _start_session(response, t)
    return {"teacher": teacher_out(t)}


@router.post("/auth/demo")
def demo_login(request: Request, response: Response, db: Session = Depends(get_db)):
    """Signs in to the sandbox demo account (fictional sample data; see services/demo.py)."""
    _require_local(request, "The demo account")
    if not config.ENABLE_DEMO:
        raise HTTPException(403, "The demo account is turned off.")
    t = ensure_demo(db)
    audit(db, t.id, "demo_login", "teacher", t.id)
    db.commit()
    _start_session(response, t)
    return {"teacher": teacher_out(t)}


@router.post("/setup", status_code=201)
def first_run_setup(body: TeacherCreateIn, response: Response, db: Session = Depends(get_db)):
    """Create the first administrator and sign in. Refused forever once any account exists."""
    if real_teacher_exists(db):
        raise HTTPException(409, "Setup is already complete. Sign in instead.")
    if _reserved(body.username):
        raise HTTPException(409, "That username is reserved. Please choose another.")
    t = Teacher(username=body.username.lower(), email=body.email, full_name=body.full_name, role="admin",
                password_hash=hash_password(body.password))
    db.add(t)
    db.flush()
    audit(db, t.id, "first_run_setup", "teacher", t.id)
    db.commit()
    response.set_cookie(config.SESSION_COOKIE, make_token(t.id, t.session_epoch), httponly=True,
                        samesite="strict", max_age=config.SESSION_HOURS * 3600, path="/")
    return {"teacher": teacher_out(t)}


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    ident = body.username.strip().lower()
    t = db.query(Teacher).filter(or_(Teacher.username == ident, Teacher.email == ident)).first()
    if t and t.locked_until and t.locked_until > utcnow():
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    ok = verify_password(body.password, t.password_hash if t else DUMMY_HASH)
    if not t or not ok or not t.is_active:
        if t:
            t.failed_logins += 1
            if t.failed_logins >= config.MAX_FAILED_LOGINS:
                t.locked_until = utcnow() + timedelta(minutes=config.LOCKOUT_MINUTES)
                t.failed_logins = 0
            audit(db, t.id, "login_failed", "teacher", t.id)
            db.commit()
        raise HTTPException(401, "Incorrect username or password.")
    t.failed_logins, t.locked_until = 0, None
    audit(db, t.id, "login", "teacher", t.id)
    db.commit()
    response.set_cookie(config.SESSION_COOKIE, make_token(t.id, t.session_epoch), httponly=True,
                        samesite="strict", max_age=config.SESSION_HOURS * 3600, path="/")
    return {"teacher": teacher_out(t)}


@router.post("/auth/logout")
def logout(response: Response, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    t.session_epoch += 1  # revokes every outstanding token for this account
    audit(db, t.id, "logout", "teacher", t.id)
    db.commit()
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(t: Teacher = Depends(current_teacher)):
    return {"teacher": teacher_out(t), "app": {"name": config.APP_NAME, "version": config.APP_VERSION,
                                               "tagline": config.TAGLINE}}


@router.put("/auth/profile")
def update_profile(body: ProfileIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    if db.query(Teacher).filter(Teacher.email == body.email, Teacher.id != t.id).first():
        raise HTTPException(409, "That email address is already in use.")
    t.full_name, t.email = body.full_name, body.email
    audit(db, t.id, "profile_update", "teacher", t.id)
    db.commit()
    return {"teacher": teacher_out(t)}


@router.post("/auth/password")
def change_password(body: PasswordIn, response: Response, t: Teacher = Depends(current_teacher),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, t.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    t.password_hash = hash_password(body.new_password)
    t.session_epoch += 1
    audit(db, t.id, "password_change", "teacher", t.id)
    db.commit()
    response.set_cookie(config.SESSION_COOKIE, make_token(t.id, t.session_epoch), httponly=True,
                        samesite="strict", max_age=config.SESSION_HOURS * 3600, path="/")
    return {"ok": True}


@router.get("/teachers")
def list_teachers(admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": [teacher_out(t) for t in db.query(Teacher).order_by(Teacher.full_name).all()]}


@router.post("/teachers", status_code=201)
def create_teacher(body: TeacherCreateIn, admin: Teacher = Depends(require_admin), db: Session = Depends(get_db)):
    uname = body.username.lower()
    if _reserved(uname):
        raise HTTPException(409, "That username is reserved. Please choose another.")
    if db.query(Teacher).filter((Teacher.username == uname) | (Teacher.email == body.email)).first():
        raise HTTPException(409, "Username or email already exists.")
    t = Teacher(username=uname, email=body.email, full_name=body.full_name, role=body.role,
                password_hash=hash_password(body.password))
    db.add(t)
    db.flush()
    audit(db, admin.id, "teacher_create", "teacher", t.id, role=t.role)
    db.commit()
    return teacher_out(t)
