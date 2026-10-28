import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="attendeye_test_")
os.environ["ATTENDEYE_DATA_DIR"] = _tmp  # must be set before the app is imported

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import recognition  # noqa: E402
from scripts.create_teacher import create  # noqa: E402

H = {"X-Requested-With": "AttendEye"}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    recognition.reset_state()
    from app.cv.service import face_service
    face_service.invalidate_gallery()
    create("admin", "admin@pub.test", "Admin User", "Admin-pass-1", admin=True)
    create("teach1", "t1@pub.test", "Teacher One", "Teach-pass-1")
    create("teach2", "t2@pub.test", "Teacher Two", "Teach-pass-2")
    yield


def make_client(user=None, pw=None):
    c = TestClient(app, headers=H)
    if user:
        r = c.post("/api/auth/login", json={"username": user, "password": pw})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture
def admin():
    return make_client("admin", "Admin-pass-1")


@pytest.fixture
def teacher():
    return make_client("teach1", "Teach-pass-1")


@pytest.fixture
def teacher2():
    return make_client("teach2", "Teach-pass-2")


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def mk_student(c, sid="S1001", name="Ayesha Rahman", section="A"):
    r = c.post("/api/students", json={"student_id": sid, "full_name": name, "department": "CSE", "section": section})
    assert r.status_code == 201, r.text
    return r.json()


def mk_class(c, code="CSE101", section="A"):
    r = c.post("/api/classes", json={"code": code, "name": "Intro to Computing", "section": section})
    assert r.status_code == 201, r.text
    return r.json()


def mk_session(c, class_id, date="2026-10-25", start="09:00", end="10:30", active=False):
    r = c.post("/api/sessions", json={"class_id": class_id, "session_date": date, "start_time": start, "end_time": end})
    assert r.status_code == 201, r.text
    s = r.json()
    if active:
        assert c.post(f"/api/sessions/{s['id']}/start").status_code == 200
    return s
