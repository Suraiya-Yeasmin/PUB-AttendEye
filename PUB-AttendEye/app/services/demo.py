"""Demo account: a sandbox teacher with fictional sample data, so the app can be explored without setup.

* The account has no usable password; it is entered only through the "Try the demo" button, which the server
  honours only for requests from this computer.
* All sample students use IDs starting with DEMO- and are hidden from every real account (and real accounts
  cannot use that prefix), so demo data never mixes with real records.
* Sample data is fictional. Demo students have NO face templates: enroll a volunteer (with consent) to try the camera.
"""
import secrets
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .. import config
from ..models import Attendance, ClassCourse, ClassSession, Student, Teacher, utcnow
from ..security import hash_password
from .attendance import record_attendance

SAMPLE_STUDENTS = [
    ("DEMO-001", "Ayesha Rahman"), ("DEMO-002", "Imran Hossain"), ("DEMO-003", "Nusrat Jahan"),
    ("DEMO-004", "Tanvir Ahmed"), ("DEMO-005", "Sadia Islam"), ("DEMO-006", "Rafi Chowdhury"),
    ("DEMO-007", "Mim Akter"), ("DEMO-008", "Farhan Kabir"),
]
# attendance pattern for the three past sessions: indexes of students who were present / late
PAST = [(14, [0, 1, 2, 3, 4, 5, 6], [7]), (7, [0, 1, 2, 4, 5, 7], [3]), (3, [0, 1, 3, 4, 5, 6, 7], [])]


def is_demo(teacher) -> bool:
    return bool(teacher) and teacher.username == config.DEMO_USERNAME


def scope_students(query, teacher):
    """Demo user sees only demo students; everyone else sees none of them."""
    like = Student.student_id.like(config.DEMO_ID_PREFIX + "%")
    return query.filter(like) if is_demo(teacher) else query.filter(~like)


def real_teacher_exists(db: Session) -> bool:
    return db.query(Teacher.id).filter(Teacher.username != config.DEMO_USERNAME).first() is not None


def ensure_demo(db: Session) -> Teacher:
    """Creates (once) and returns the demo teacher with its sample class, students and sessions."""
    t = db.query(Teacher).filter(Teacher.username == config.DEMO_USERNAME).first()
    if not t:
        t = Teacher(username=config.DEMO_USERNAME, email="demo@attendeye.local", full_name="Demo Teacher",
                    role="teacher", password_hash=hash_password(secrets.token_urlsafe(32)))
        db.add(t)
        db.flush()
    if db.query(ClassCourse).filter_by(teacher_id=t.id, code="DEMO101").first():
        db.commit()
        return t
    students = []
    for sid, name in SAMPLE_STUDENTS:
        s = db.query(Student).filter(Student.student_id == sid).first()
        if not s:
            s = Student(student_id=sid, full_name=name, department="Demo (sample data)", section="A",
                        email=f"{sid.lower()}@demo.local")
            db.add(s)
        students.append(s)
    db.flush()
    course = ClassCourse(code="DEMO101", name="Introduction to Smart Attendance (sample class)", section="A",
                         department="Demo (sample data)", teacher_id=t.id)
    course.students = students
    db.add(course)
    db.flush()
    today = date.today()
    for days_ago, present, late in PAST:
        sess = ClassSession(class_id=course.id, session_date=today - timedelta(days=days_ago), start_time="09:00",
                            end_time="10:30", status="completed", started_at=utcnow() - timedelta(days=days_ago),
                            ended_at=utcnow() - timedelta(days=days_ago, hours=-1))
        db.add(sess)
        db.flush()
        for i in present:
            db.add(Attendance(session_id=sess.id, student_pk=students[i].id, method="manual", status="present",
                              created_by=t.id, note="Sample data"))
        for i in late:
            db.add(Attendance(session_id=sess.id, student_pk=students[i].id, method="manual", status="late",
                              created_by=t.id, note="Sample data"))
    live = ClassSession(class_id=course.id, session_date=today, start_time="09:00", end_time="10:30",
                        status="active", started_at=utcnow())
    db.add(live)
    db.flush()
    for i in (0, 1, 4):
        record_attendance(db, live, students[i], method="manual", teacher_id=t.id, note="Sample data")
    db.commit()
    return t
