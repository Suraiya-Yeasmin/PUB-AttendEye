"""Workflow tests with the camera/model mocked. Real-webcam behaviour is covered by MANUAL_TESTS.md."""
import threading
from datetime import date

import numpy as np
import pytest

from app.cv.service import CVUnavailable, face_service
from app.database import SessionLocal
from app.models import Attendance, EvaluationSample, RecognitionEvent
from app.services import recognition
from app.services import trustscore as ts
from tests.conftest import H, make_client, mk_class, mk_session, mk_student

FACE = np.array([100, 100, 120, 140] + [0.0] * 10 + [0.99])
GOOD_Q = {"ok": True, "issues": [], "messages": [], "metrics": {"detector_score": 0.99, "face_px": 120,
          "sharpness": 200.0, "brightness": 130, "head_turn": 0.0, "head_tilt_deg": 0.0}}
BAD_Q = {**GOOD_Q, "ok": False, "issues": ["blurry"], "messages": ["The image is blurry."]}


def fake_frames(monkeypatch, items):
    """items: [{'pk': student pk or None, 'sim': float|None, 'runner': float|None, 'q': GOOD_Q|BAD_Q}]"""
    def analyze(img, settings, gallery):
        policy = ts.Policy.from_settings(settings)
        out = []
        for it in items:
            q = it.get("q", GOOD_Q)
            a = {"face": FACE, "quality": q, "student_pk": None, "similarity": None, "runner_up": None,
                 "decision": ts.POOR_QUALITY, "reason": " ".join(q["messages"]), "embedding": None}
            if q["ok"]:
                d, r = ts.decide(it["sim"], it.get("runner"), policy)
                a.update(student_pk=it["pk"], similarity=it["sim"], runner_up=it.get("runner"), decision=d, reason=r)
            out.append(a)
        return [FACE] * len(out), out
    monkeypatch.setattr(recognition, "analyze_frame", analyze)
    monkeypatch.setattr(face_service, "decode", lambda data, max_side=960: np.zeros((480, 640, 3), np.uint8))
    monkeypatch.setattr(face_service, "gallery", lambda db: ([], None))
    monkeypatch.setattr(face_service, "thumbnail", lambda img, face: b"jpeg-bytes")


def send(c, sid):
    return c.post(f"/api/recognition/frame?session_id={sid}", content=b"frame", headers={"Content-Type": "image/jpeg"})


def setup(c, n=2):
    studs = [mk_student(c, f"S10{i}", f"Student {i}") for i in range(n)]
    cls = mk_class(c)
    assert c.put(f"/api/classes/{cls['id']}/roster", json={"student_pks": [s["id"] for s in studs]}).status_code == 200
    return studs, cls, mk_session(c, cls["id"], date=date.today().isoformat(), active=True)


def count_att(sid):
    with SessionLocal() as db:
        return db.query(Attendance).filter_by(session_id=sid).count()


# ---------------------------------------------------------------- decision policy (pure rules)
def test_policy_rules_are_transparent():
    p = ts.Policy(accept=0.5, review=0.363, margin=0.05)
    assert ts.decide(None, None, p)[0] == ts.UNKNOWN
    assert ts.decide(0.2, None, p)[0] == ts.UNKNOWN
    assert ts.decide(0.45, 0.1, p)[0] == ts.NEEDS_REVIEW
    assert ts.decide(0.70, 0.68, p)[0] == ts.NEEDS_REVIEW        # competing candidates, margin too small
    assert ts.decide(0.70, 0.30, p)[0] == ts.ACCEPTED
    for sim, run in [(0.2, None), (0.45, 0.1), (0.7, 0.68)]:
        assert len(ts.decide(sim, run, p)[1]) > 20                  # every non-accept has a reason


# ---------------------------------------------------------------- recognition -> attendance
def test_unknown_face_is_never_marked_present(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[0]["id"], "sim": 0.2, "runner": 0.1}])
    r = send(teacher, s["id"]).json()
    assert r["faces"][0]["state"] == "unknown" and r["faces"][0]["candidate"] is None
    assert count_att(s["id"]) == 0
    assert teacher.get("/api/dashboard").json()["cards"]["unknown_detected"] == 1


def test_poor_quality_creates_no_event_or_attendance(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[0]["id"], "sim": 0.9, "q": BAD_Q}])
    r = send(teacher, s["id"]).json()
    assert r["faces"][0]["state"] == "poor_quality" and r["faces"][0]["candidate"] is None
    with SessionLocal() as db:
        assert db.query(RecognitionEvent).count() == 0
    assert count_att(s["id"]) == 0


def test_accept_needs_consecutive_frames_then_duplicate_is_blocked(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[0]["id"], "sim": 0.8, "runner": 0.2}])
    assert send(teacher, s["id"]).json()["faces"][0]["state"] == "pending"
    assert count_att(s["id"]) == 0                                  # one frame is not enough
    assert send(teacher, s["id"]).json()["faces"][0]["state"] == "verified"
    assert count_att(s["id"]) == 1
    for _ in range(3):                                              # repeated requests
        assert send(teacher, s["id"]).json()["faces"][0]["state"] == "duplicate"
    assert count_att(s["id"]) == 1


def test_uncertain_match_goes_to_review_and_reports_distinguish_it(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[1]["id"], "sim": 0.44, "runner": 0.1}])
    r = send(teacher, s["id"]).json()["faces"][0]
    assert r["state"] == "review" and r["trust"]["review_required"] and "below" in r["trust"]["reason"]
    send(teacher, s["id"])                                          # repeated frames do not stack review cases
    assert count_att(s["id"]) == 0
    q = teacher.get("/api/review").json()
    assert len(q["items"]) == 1 and q["pending_total"] == 1

    row = teacher.get("/api/reports/summary").json()["sessions"][0]
    assert row["pending_review"] == 1 and row["present"] == 0 and row["absent"] == 1   # 2 roster - 1 pending
    csv = teacher.get(f"/api/reports/export?kind=session&session_id={s['id']}").text
    assert "pending_review" in csv and "absent" in csv

    d = teacher.post(f"/api/review/{q['items'][0]['id']}/decision", json={"action": "confirm"})
    assert d.status_code == 200 and count_att(s["id"]) == 1
    row = teacher.get("/api/reports/summary").json()["sessions"][0]
    assert row["pending_review"] == 0 and row["present"] == 1


def test_close_competitors_trigger_review_with_margin_reason(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[0]["id"], "sim": 0.75, "runner": 0.73}])
    r = send(teacher, s["id"]).json()["faces"][0]
    assert r["state"] == "review" and "margin" in r["trust"]["reason"]


def test_matched_student_not_on_roster_needs_teacher_confirmation(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    outsider = mk_student(teacher, "OUT1", "Outsider")
    fake_frames(monkeypatch, [{"pk": outsider["id"], "sim": 0.9, "runner": 0.1}])
    r = send(teacher, s["id"]).json()["faces"][0]
    assert r["state"] == "review" and "roster" in r["trust"]["reason"]
    assert count_att(s["id"]) == 0


def test_closed_session_rejects_and_creates_nothing(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[0]["id"], "sim": 0.9, "runner": 0.1}])
    teacher.post(f"/api/sessions/{s['id']}/close")
    assert send(teacher, s["id"]).status_code == 409
    assert count_att(s["id"]) == 0


def test_multiple_faces_are_each_decided_independently(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[0]["id"], "sim": 0.2}, {"pk": studs[1]["id"], "sim": 0.44, "runner": 0.1}])
    states = [f["state"] for f in send(teacher, s["id"]).json()["faces"]]
    assert states == ["unknown", "review"] and count_att(s["id"]) == 0


def test_model_unavailable_is_reported_not_simulated(teacher, monkeypatch):
    studs, cls, s = setup(teacher)
    def boom(*a, **k): raise CVUnavailable("Model file missing: face_recognition_sface_2021dec.onnx")
    monkeypatch.setattr(face_service, "decode", lambda data, max_side=960: np.zeros((10, 10, 3), np.uint8))
    monkeypatch.setattr(recognition, "analyze_frame", boom)
    r = send(teacher, s["id"])
    assert r.status_code == 503 and "unavailable" in r.json()["detail"].lower() and count_att(s["id"]) == 0


# ---------------------------------------------------------------- enrollment validation
@pytest.fixture
def cv_ok(monkeypatch):
    monkeypatch.setattr(face_service, "status", lambda: {"available": True, "error": None})


def test_enrollment_validation(teacher, cv_ok, monkeypatch):
    st = mk_student(teacher)
    assert teacher.post("/api/enrollment/start", json={"student_pk": st["id"], "consent": False}).status_code == 400
    assert teacher.post("/api/enrollment/start", json={"student_pk": 999, "consent": True}).status_code == 404
    assert teacher.post(f"/api/enrollment/frame/{st['id']}", content=b"x").status_code == 409   # not started
    teacher.post(f"/api/students/{st['id']}/deactivate")
    assert teacher.post("/api/enrollment/start", json={"student_pk": st["id"], "consent": True}).status_code == 409
    teacher.post(f"/api/students/{st['id']}/activate")
    assert teacher.post("/api/enrollment/start", json={"student_pk": st["id"], "consent": True}).status_code == 200
    monkeypatch.setattr(face_service, "decode", lambda d, max_side=960: np.zeros((480, 640, 3), np.uint8))
    monkeypatch.setattr(face_service, "detect", lambda img: [])
    assert teacher.post(f"/api/enrollment/frame/{st['id']}", content=b"x").json()["status"] == "no_face"
    monkeypatch.setattr(face_service, "detect", lambda img: [FACE, FACE])
    r = teacher.post(f"/api/enrollment/frame/{st['id']}", content=b"x").json()
    assert r["status"] == "multiple_faces" and "Multiple faces" in r["message"]
    monkeypatch.setattr(face_service, "detect", lambda img: [FACE])
    monkeypatch.setattr(face_service, "assess_quality", lambda img, f, s: BAD_Q)
    r = teacher.post(f"/api/enrollment/frame/{st['id']}", content=b"x").json()
    assert r["status"] == "poor_quality" and r["count"] == 0
    assert teacher.get(f"/api/students/{st['id']}").json()["face_enrolled"] is False


def test_enrollment_unavailable_service_blocks_start(teacher, monkeypatch):
    st = mk_student(teacher)
    monkeypatch.setattr(face_service, "status", lambda: {"available": False, "error": "Model file missing"})
    assert teacher.post("/api/enrollment/start", json={"student_pk": st["id"], "consent": True}).status_code == 503


# ---------------------------------------------------------------- classes, sessions, invalid input
def test_session_and_class_validation(teacher):
    cls = mk_class(teacher)
    base = {"class_id": cls["id"], "session_date": "2026-10-25", "start_time": "09:00", "end_time": "10:00"}
    assert teacher.post("/api/sessions", json={**base, "end_time": "08:00"}).status_code == 422
    assert teacher.post("/api/sessions", json={**base, "start_time": "9am"}).status_code == 422
    assert teacher.post("/api/sessions", json={**base, "session_date": "not-a-date"}).status_code == 422
    assert teacher.post("/api/sessions", json={**base, "class_id": 999}).status_code == 404
    assert teacher.post("/api/sessions", json=base).status_code == 201
    assert teacher.post("/api/sessions", json=base).status_code == 409
    assert teacher.post("/api/classes", json={"code": "", "name": "x", "section": "A"}).status_code == 422
    assert teacher.post("/api/classes", json={"code": "CSE101", "name": "Dup", "section": "A"}).status_code == 409
    r = teacher.post("/api/students", json={"student_id": "ab", "full_name": "", "department": "", "section": ""})
    assert r.status_code == 422 and "fields" in r.json()["detail"]
    assert teacher.get("/api/attendance?date_from=bad").status_code == 400


def test_only_one_active_session_per_class(teacher):
    cls = mk_class(teacher)
    a = mk_session(teacher, cls["id"], start="08:00", end="09:00", active=True)
    b = mk_session(teacher, cls["id"], start="10:00", end="11:00")
    assert teacher.post(f"/api/sessions/{b['id']}/start").status_code == 409


# ---------------------------------------------------------------- manual path, concurrency, history
def test_manual_attendance_rules_and_concurrent_duplicates(teacher):
    studs, cls, s = setup(teacher)
    outsider = mk_student(teacher, "OUT2", "Outsider")
    body = {"session_id": s["id"], "student_pk": studs[0]["id"]}
    assert teacher.post("/api/attendance/manual", json={**body, "student_pk": outsider["id"]}).status_code == 409
    codes = []
    def go():
        c = make_client("teach1", "Teach-pass-1")
        codes.append(c.post("/api/attendance/manual", json=body).status_code)
    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert codes.count(201) == 1 and codes.count(409) == 5 and count_att(s["id"]) == 1


def test_history_filters_sort_and_pagination(teacher):
    studs, cls, s = setup(teacher, 3)
    teacher.post("/api/attendance/manual", json={"session_id": s["id"], "student_pk": studs[0]["id"]})
    teacher.post("/api/attendance/manual", json={"session_id": s["id"], "student_pk": studs[1]["id"], "status": "late"})
    teacher.post("/api/attendance/manual", json={"session_id": s["id"], "student_pk": studs[2]["id"], "status": "excused"})
    g = lambda q: teacher.get("/api/attendance?" + q).json()
    assert g("")["total"] == 3
    assert g("status=late")["total"] == 1
    assert g("method=manual")["total"] == 3 and g("method=face")["total"] == 0
    assert g("q=Student 1")["items"][0]["student_name"] == "Student 1"
    assert g(f"session_id={s['id']}&class_id={cls['id']}")["total"] == 3
    assert g("date_from=2999-01-01")["total"] == 0
    names = [i["student_name"] for i in g("sort=student_name&direction=desc")["items"]]
    assert names == sorted(names, reverse=True)
    p = g("page=2&page_size=2")
    assert len(p["items"]) == 1 and p["total"] == 3


def test_history_and_reports_are_isolated_between_teachers(teacher, teacher2):
    studs, cls, s = setup(teacher)
    teacher.post("/api/attendance/manual", json={"session_id": s["id"], "student_pk": studs[0]["id"]})
    assert teacher2.get("/api/attendance").json()["total"] == 0
    assert teacher2.get("/api/reports/summary").json()["sessions"] == []
    assert teacher2.get(f"/api/reports/export?kind=session&session_id={s['id']}").status_code == 403
    assert teacher2.get("/api/attendance/1").status_code == 403


def test_csv_headers_and_empty_export(teacher):
    csv = teacher.get("/api/reports/export?kind=history")
    assert csv.status_code == 200 and csv.headers["X-Row-Count"] == "0" and csv.text.lstrip("﻿").startswith("Student ID")
    assert teacher.get("/api/reports/export?kind=nonsense").status_code == 422


# ---------------------------------------------------------------- dashboard + evaluation maths
def test_dashboard_glance_counts_match_database(teacher):
    studs, cls, s = setup(teacher)
    teacher.post("/api/attendance/manual", json={"session_id": s["id"], "student_pk": studs[0]["id"]})
    g = teacher.get("/api/dashboard").json()
    assert g["glance"] == {"classes": 1, "sessions": 1, "sessions_today": 1, "checkins_today": 1}
    assert g["cards"]["present"] == 1 and g["cards"]["absent"] == 1


def test_evaluation_threshold_sweep_is_computed_from_samples(teacher):
    studs, cls, s = setup(teacher)
    pk = studs[0]["id"]
    def add(truth, pred, sim):
        with SessionLocal() as db:
            db.add(EvaluationSample(truth_student_pk=truth, predicted_student_pk=pred, similarity=sim,
                                    decision="accepted", quality_status="ok", processing_ms=10.0,
                                    accept_threshold=0.5, review_threshold=0.363)); db.commit()
    add(pk, pk, 0.80); add(pk, pk, 0.45); add(None, pk, 0.55); add(None, pk, 0.30)
    sw = {r["threshold"]: r for r in teacher.get("/api/evaluation/summary").json()["threshold_sweep"]}
    assert sw[0.40]["genuine_accepted"] == 2 and sw[0.40]["impostor_accepted"] == 1
    assert sw[0.50]["genuine_accepted"] == 1 and sw[0.50]["genuine_missed"] == 1 and sw[0.50]["false_accepts"] == 1
    assert sw[0.80]["false_accepts"] == 0 and sw[0.80]["false_reject_rate"] == 0.5
    assert teacher.get("/api/evaluation/summary").json()["small_sample_warning"] is True


def test_live_evaluation_counters_are_scoped_to_own_classes(teacher, teacher2, monkeypatch):
    studs, cls, s = setup(teacher)
    fake_frames(monkeypatch, [{"pk": studs[0]["id"], "sim": 0.2}])
    send(teacher, s["id"])                                   # one unknown event in teacher 1's class
    assert teacher.get("/api/evaluation/summary").json()["live"]["unknown"] == 1
    assert teacher2.get("/api/evaluation/summary").json()["live"]["unknown"] == 0
