"""First-run setup used by the installed desktop app (replaces scripts/create_teacher.py)."""
from app.database import SessionLocal
from app.models import Teacher
from tests.conftest import H, make_client

BODY = {"full_name": "Dr Test Owner", "email": "Owner@Pub.test", "username": "Owner", "password": "Owner-pass-1"}


def _wipe_teachers():
    with SessionLocal() as db:
        db.query(Teacher).delete()
        db.commit()


def test_setup_status_and_creates_first_admin_then_locks():
    _wipe_teachers()
    c = make_client()
    assert c.get("/api/setup/status").json() == {"needs_setup": True}
    r = c.post("/api/setup", json=BODY)
    assert r.status_code == 201
    assert r.json()["teacher"]["role"] == "admin"
    assert c.get("/api/auth/me").status_code == 200          # signed in by the cookie from setup
    assert c.get("/api/setup/status").json() == {"needs_setup": False}
    assert make_client().post("/api/setup", json={**BODY, "username": "second", "email": "s@pub.test"}).status_code == 409
    assert make_client("owner", "Owner-pass-1").get("/api/auth/me").status_code == 200  # username lower-cased


def test_setup_refused_when_accounts_exist(admin):
    assert make_client().get("/api/setup/status").json() == {"needs_setup": False}
    assert make_client().post("/api/setup", json=BODY).status_code == 409


def test_setup_validates_and_requires_csrf_header():
    _wipe_teachers()
    c = make_client()
    assert c.post("/api/setup", json={**BODY, "password": "short"}).status_code == 422
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).post("/api/setup", json=BODY).status_code == 403
