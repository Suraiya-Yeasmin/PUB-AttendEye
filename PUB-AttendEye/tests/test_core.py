import csv
import io

from app.models import Attendance, RecognitionEvent
from tests.conftest import H, make_client, mk_class, mk_session, mk_student
from fastapi.testclient import TestClient
from app.main import app


# ---------------------------------------------------------------- auth / security
def test_login_rejects_bad_credentials_and_hides_users():
    c = TestClient(app, headers=H)
    assert c.post("/api/auth/login", json={"username": "teach1", "password": "wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401


def test_protected_endpoints_require_login_and_csrf_header():
    anon = TestClient(app)  # no CSRF header, no cookie
    assert anon.get("/api/students").status_code == 401
    assert anon.post("/api/students", json={}).status_code == 403  # CSRF header missing
    assert TestClient(app, headers=H).get("/api/students").status_code == 401


def test_lockout_after_repeated_failures():
    c = TestClient(app, headers=H)
    for _ in range(5):
        c.post("/api/auth/login", json={"username": "teach1", "password": "bad"})
    r = c.post("/api/auth/login", json={"username": "teach1", "password": "Teach-pass-1"})
    assert r.status_code == 429


def test_logout_revokes_token(teacher):
    assert teacher.get("/api/auth/me").status_code == 200
    stale = teacher.cookies.get("attendeye_session")
    teacher.post("/api/auth/logout")
    other = TestClient(app, headers=H, cookies={"attendeye_session": stale})
    assert other.get("/api/auth/me").status_code == 401


def test_password_is_hashed(db):
    from app.models import Teacher
    t = db.query(Teacher).filter_by(username="teach1").one()
    assert t.password_hash.startswith("scrypt$") and "Teach-pass-1" not in t.password_hash


# ---------------------------------------------------------------- students
def test_student_validation_and_duplicates(teacher):
    mk_student(teacher)
    dup = teacher.post("/api/students", json={"student_id": "s1001", "full_name": "Other Person",
                                              "department": "CSE", "section": "A"})
    assert dup.status_code == 409
    bad = teacher.post("/api/students", json={"student_id": "x", "full_name": "", "department": "", "section": ""})
    assert bad.status_code == 422
    assert teacher.get("/api/students?q=ayesha").json()["total"] == 1
    assert teacher.get("/api/students?q=zzz").json()["total"] == 0


def test_student_api_never_exposes_biometrics(teacher, db):
    from app.models import FaceTemplate
    from app.security import encrypt_bytes
    from datetime import datetime
    s = mk_student(teacher)
    db.add(FaceTemplate(student_pk=s["id"], embedding_enc=encrypt_bytes(b"x" * 512), model_name="t",
                        sample_count=5, consent_recorded_at=datetime(2026, 1, 1)))
    db.commit()
    body = teacher.get(f"/api/students/{s['id']}").text.lower()
    assert "embedding" not in body and "template_enc" not in body
    assert teacher.get(f"/api/students/{s['id']}").json()["face_enrolled"] is True
    assert teacher.delete(f"/api/students/{s['id']}/template").status_code == 200
    assert teacher.get(f"/api/students/{s['id']}").json()["face_enrolled"] is False
    assert teacher.get(f"/api/students/{s['id']}").json()["biometric_consent"] == "withdrawn"


def test_enrollment_requires_consent(teacher):
    s = mk_student(teacher)
    r = teacher.post("/api/enrollment/start", json={"student_pk": s["id"], "consent": False})
    assert r.status_code == 400


# ---------------------------------------------------------------- sessions & attendance
def test_session_lifecycle_and_closed_session_rejects_attendance(teacher):
    s = mk_student(teacher)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"])
    body = {"session_id": sess["id"], "student_pk": s["id"]}
    assert teacher.post("/api/attendance/manual", json=body).status_code == 409  # scheduled, not active
    assert teacher.post(f"/api/sessions/{sess['id']}/start").status_code == 200
    assert teacher.post("/api/attendance/manual", json=body).status_code == 201
    assert teacher.post("/api/attendance/manual", json=body).status_code == 409  # duplicate prevented
    assert teacher.post(f"/api/sessions/{sess['id']}/close").status_code == 200
    s2 = mk_student(teacher, "S1002", "Karim Uddin")
    assert teacher.post("/api/attendance/manual", json={"session_id": sess["id"], "student_pk": s2["id"]}).status_code == 409
    assert teacher.post(f"/api/sessions/{sess['id']}/start").status_code == 409  # completed cannot restart


def test_recognition_rejected_when_session_not_active(teacher):
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"])
    r = teacher.post(f"/api/recognition/frame?session_id={sess['id']}", content=b"123",
                     headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 409 and "Session Not Active" in r.json()["detail"]
    assert teacher.post("/api/recognition/frame?session_id=9999", content=b"123").status_code == 404


def test_recognition_reports_service_unavailable_instead_of_simulating(teacher, monkeypatch, tmp_path):
    from app import config
    from app.cv.service import face_service
    monkeypatch.setattr(config, "DETECTOR_MODEL", tmp_path / "missing.onnx")
    monkeypatch.setattr(face_service, "_det", None)
    monkeypatch.setattr(face_service, "_last_try", 0)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"], active=True)
    import cv2, numpy as np
    ok, buf = cv2.imencode(".jpg", np.zeros((120, 160, 3), np.uint8))
    r = teacher.post(f"/api/recognition/frame?session_id={sess['id']}", content=buf.tobytes())
    assert r.status_code == 503 and "unavailable" in r.json()["detail"].lower()


def test_unique_constraint_on_student_session(db, teacher):
    from sqlalchemy.exc import IntegrityError
    import pytest
    s = mk_student(teacher)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"], active=True)
    db.add(Attendance(session_id=sess["id"], student_pk=s["id"], method="manual")); db.commit()
    db.add(Attendance(session_id=sess["id"], student_pk=s["id"], method="manual"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_class_ownership_is_enforced(teacher, teacher2, admin):
    c = mk_class(teacher)
    assert teacher2.get(f"/api/classes/{c['id']}").status_code == 403
    assert teacher2.post("/api/sessions", json={"class_id": c["id"], "session_date": "2026-10-25",
                                                "start_time": "09:00", "end_time": "10:00"}).status_code == 403
    assert admin.get(f"/api/classes/{c['id']}").status_code == 200
    assert teacher2.get("/api/classes").json()["items"] == []


# ---------------------------------------------------------------- review queue
def _pending_event(db, sess_id, student_pk):
    ev = RecognitionEvent(session_id=sess_id, student_pk=student_pk, similarity=0.42, runner_up_similarity=0.1,
                          decision="needs_review", reason="between thresholds", review_status="pending")
    db.add(ev); db.commit()
    return ev.id


def test_review_confirm_revalidates_and_does_not_double_count(teacher, db):
    s = mk_student(teacher)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"])  # scheduled
    ev = _pending_event(db, sess["id"], s["id"])
    r = teacher.post(f"/api/review/{ev}/decision", json={"action": "confirm"})
    assert r.status_code == 409  # session not active -> no attendance
    assert db.query(Attendance).count() == 0
    teacher.post(f"/api/sessions/{sess['id']}/start")
    r = teacher.post(f"/api/review/{ev}/decision", json={"action": "confirm"})
    assert r.status_code == 200 and db.query(Attendance).count() == 1
    a = db.query(Attendance).one()
    assert a.method == "face_review" and a.review_status == "teacher_confirmed"
    assert teacher.post(f"/api/review/{ev}/decision", json={"action": "confirm"}).status_code == 409


def test_review_reject_and_unknown_create_no_attendance(teacher, db):
    s = mk_student(teacher)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"], active=True)
    e1, e2 = _pending_event(db, sess["id"], s["id"]), _pending_event(db, sess["id"], s["id"])
    assert teacher.post(f"/api/review/{e1}/decision", json={"action": "reject"}).status_code == 200
    assert teacher.post(f"/api/review/{e2}/decision", json={"action": "unknown"}).status_code == 200
    assert db.query(Attendance).count() == 0
    assert teacher.get("/api/review?status=pending").json()["pending_total"] == 0


def test_review_requires_class_access(teacher, teacher2, db):
    s = mk_student(teacher)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"], active=True)
    ev = _pending_event(db, sess["id"], s["id"])
    assert teacher2.post(f"/api/review/{ev}/decision", json={"action": "confirm"}).status_code == 403
    assert teacher2.get("/api/review").json()["items"] == []


# ---------------------------------------------------------------- history, corrections, CSV
def test_correction_is_audited_and_removal_marks_absent(teacher):
    s = mk_student(teacher)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"], active=True)
    a = teacher.post("/api/attendance/manual", json={"session_id": sess["id"], "student_pk": s["id"]}).json()
    assert teacher.put(f"/api/attendance/{a['id']}", json={"status": "late", "note": ""}).status_code == 422
    r = teacher.put(f"/api/attendance/{a['id']}", json={"status": "late", "note": "arrived 20 min late"})
    assert r.status_code == 200 and r.json()["corrected"] is True
    trail = teacher.get(f"/api/attendance/{a['id']}").json()["audit"]
    assert any(t["action"] == "attendance_correct" for t in trail)
    assert teacher.post(f"/api/attendance/{a['id']}/remove", json={"reason": "wrong student"}).status_code == 200
    assert teacher.get("/api/attendance").json()["total"] == 0


def test_csv_export_real_data_and_formula_protection(teacher):
    s = mk_student(teacher, "S2001", "=HYPERLINK(\"http://evil\")")
    c = mk_class(teacher)
    teacher.put(f"/api/classes/{c['id']}/roster", json={"student_pks": [s["id"]]})
    sess = mk_session(teacher, c["id"], active=True)
    teacher.post("/api/attendance/manual", json={"session_id": sess["id"], "student_pk": s["id"]})
    r = teacher.get(f"/api/reports/export?kind=session&session_id={sess['id']}")
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Student ID" and rows[1][0] == "S2001" and rows[1][4] == "present"
    assert rows[1][1].startswith("'=")  # neutralised
    assert r.headers["x-row-count"] == "1"


def test_empty_report_returns_header_only_and_summary_has_no_fake_numbers(teacher):
    r = teacher.get("/api/reports/export?kind=history")
    assert r.status_code == 200 and r.headers["x-row-count"] == "0"
    summ = teacher.get("/api/reports/summary").json()
    assert summ["sessions"] == [] and summ["totals"]["average_percentage"] is None


def test_report_percentage_uses_roster(teacher):
    a, b = mk_student(teacher), mk_student(teacher, "S1002", "Karim Uddin")
    c = mk_class(teacher)
    teacher.put(f"/api/classes/{c['id']}/roster", json={"student_pks": [a["id"], b["id"]]})
    sess = mk_session(teacher, c["id"], active=True)
    teacher.post("/api/attendance/manual", json={"session_id": sess["id"], "student_pk": a["id"]})
    row = teacher.get("/api/reports/summary").json()["sessions"][0]
    assert (row["present"], row["absent"], row["percentage"]) == (1, 1, 50.0)


# ---------------------------------------------------------------- settings, evaluation, dashboard
def test_protected_settings_need_admin_and_are_validated(teacher, admin):
    assert teacher.put("/api/settings", json={"values": {"accept_threshold": 0.6}}).status_code == 403
    assert teacher.put("/api/settings", json={"values": {"default_session_minutes": 60}}).status_code == 200
    assert admin.put("/api/settings", json={"values": {"accept_threshold": 5}}).status_code == 422
    assert admin.put("/api/settings", json={"values": {"accept_threshold": 0.3, "review_threshold": 0.4}}).status_code == 422
    assert admin.put("/api/settings", json={"values": {"accept_threshold": 0.6}}).status_code == 200
    assert admin.get("/api/settings").json()["values"]["accept_threshold"] == 0.6


def test_evaluation_not_evaluated_until_samples_exist(teacher):
    j = teacher.get("/api/evaluation/summary").json()
    assert j["evaluated"] is False and j["samples"] == 0
    assert j["false_accept_rate"] is None and j["avg_processing_ms"] is None


def test_dashboard_uses_real_data_and_empty_states(teacher):
    j = teacher.get("/api/dashboard").json()
    assert j["empty"]["no_classes"] and j["empty"]["no_students"] and j["cards"]["present"] is None
    s = mk_student(teacher)
    c = mk_class(teacher)
    sess = mk_session(teacher, c["id"], active=True)
    teacher.put(f"/api/classes/{c['id']}/roster", json={"student_pks": [s["id"]]})
    teacher.post("/api/attendance/manual", json={"session_id": sess["id"], "student_pk": s["id"]})
    j = teacher.get("/api/dashboard").json()
    assert j["cards"]["present"] == 1 and j["cards"]["absent"] == 0 and j["selected_session"]["status"] == "active"


def test_purge_biometrics_needs_admin_and_confirmation(teacher, admin):
    assert teacher.post("/api/settings/purge-biometrics", json={"confirm": "DELETE ALL TEMPLATES"}).status_code == 403
    assert admin.post("/api/settings/purge-biometrics", json={"confirm": "no"}).status_code == 422
    assert admin.post("/api/settings/purge-biometrics", json={"confirm": "DELETE ALL TEMPLATES"}).status_code == 200
