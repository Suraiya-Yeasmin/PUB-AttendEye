"""Self-service sign-up and the demo account."""
from fastapi.testclient import TestClient

from app import config
from app.main import app
from tests.conftest import H, make_client

NEW = {"full_name": "New Teacher", "email": "new@pub.test", "username": "newteacher", "password": "New-pass-123"}


def test_options_report_features_for_local_client(admin):
    o = make_client().get("/api/auth/options").json()
    assert o == {"needs_setup": False, "signup_enabled": True, "demo_enabled": True}


def test_register_creates_teacher_not_admin_and_signs_in(admin):
    c = make_client()
    r = c.post("/api/auth/register", json={**NEW, "role": "admin"})  # role in body must be ignored
    assert r.status_code == 201 and r.json()["teacher"]["role"] == "teacher"
    assert c.get("/api/auth/me").status_code == 200
    assert c.get("/api/teachers").status_code == 403                    # not an administrator
    assert make_client("newteacher", "New-pass-123").get("/api/auth/me").status_code == 200


def test_register_rejects_duplicates_reserved_and_weak(admin):
    c = make_client()
    assert c.post("/api/auth/register", json=NEW).status_code == 201
    assert make_client().post("/api/auth/register", json=NEW).status_code == 409
    assert make_client().post("/api/auth/register", json={**NEW, "username": "DEMO", "email": "d@pub.test"}).status_code == 409
    assert make_client().post("/api/auth/register", json={**NEW, "username": "x2", "email": "q@pub.test"}).status_code == 422
    assert make_client().post("/api/auth/register", json={**NEW, "password": "short", "email": "q@pub.test"}).status_code == 422


def test_register_needs_admin_first_and_can_be_disabled(admin, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_SIGNUP", False)
    assert make_client().post("/api/auth/register", json=NEW).status_code == 403
    assert make_client().get("/api/auth/options").json()["signup_enabled"] is False


def test_register_and_demo_refused_from_other_machines(admin):
    remote = TestClient(app, client=("203.0.113.9", 5555), headers=H)
    assert remote.post("/api/auth/register", json=NEW).status_code == 403
    assert remote.post("/api/auth/demo").status_code == 403
    o = remote.get("/api/auth/options").json()
    assert o["signup_enabled"] is False and o["demo_enabled"] is False


def test_demo_login_has_sample_data_and_is_idempotent(admin):
    c = make_client()
    assert c.post("/api/auth/demo").status_code == 200
    me = c.get("/api/auth/me").json()["teacher"]
    assert me["username"] == "demo" and me["role"] == "teacher"
    classes = c.get("/api/classes").json()["items"]
    assert [x["code"] for x in classes] == ["DEMO101"]
    assert c.get("/api/students").json()["total"] == 8
    assert c.post("/api/auth/demo").status_code == 200                  # second click: no duplicates
    assert c.get("/api/students").json()["total"] == 8
    assert len(c.get("/api/sessions").json()["items"]) == 4
    d = c.get("/api/dashboard").json()
    assert d["cards"]["total_students"] == 8 and d["cards"]["present"] == 3


def test_demo_has_no_usable_password_and_cannot_be_created_by_others(admin):
    make_client().post("/api/auth/demo")
    assert make_client().post("/api/auth/login", json={"username": "demo", "password": "demo"}).status_code == 401
    a = make_client("admin", "Admin-pass-1")
    r = a.post("/api/teachers", json={**NEW, "username": "demo", "email": "d2@pub.test"})
    assert r.status_code == 409


def test_demo_data_is_hidden_from_real_accounts_and_vice_versa(admin):
    demo = make_client(); demo.post("/api/auth/demo")
    a = make_client("admin", "Admin-pass-1")
    assert a.get("/api/students").json()["total"] == 0                    # no demo students for a real admin
    assert a.get("/api/dashboard").json()["cards"]["total_students"] == 0
    body = {"student_id": "S-100", "full_name": "Real Student", "department": "CSE", "section": "A"}
    assert a.post("/api/students", json=body).status_code == 201
    assert a.post("/api/students", json={**body, "student_id": "DEMO-099"}).status_code == 422
    assert demo.get("/api/students").json()["total"] == 8                 # real students invisible to demo
    assert demo.post("/api/students", json={**body, "student_id": "S-101"}).status_code == 422


def test_demo_does_not_count_as_first_run_setup():
    from app.database import SessionLocal
    from app.models import Teacher
    with SessionLocal() as db:
        db.query(Teacher).delete(); db.commit()
    c = make_client()
    assert c.post("/api/auth/demo").status_code == 200                    # explore before creating an account
    assert make_client().get("/api/setup/status").json() == {"needs_setup": True}
    r = make_client().post("/api/setup", json={"full_name": "Owner", "email": "o@pub.test", "username": "owner",
                                                "password": "Owner-pass-1"})
    assert r.status_code == 201 and r.json()["teacher"]["role"] == "admin"
