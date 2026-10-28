from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..cv.service import face_service
from ..database import get_db
from ..deps import current_teacher
from ..models import Student, Teacher
from ..schemas import ConsentIn, StudentIn
from ..serializers import student_out
from ..services.audit import audit
from ..services.demo import is_demo, scope_students
from .. import config

router = APIRouter(prefix="/api/students", tags=["students"])


def _get(db: Session, pk: int) -> Student:
    s = db.get(Student, pk)
    if not s:
        raise HTTPException(404, "Student not found.")
    return s


@router.get("")
def list_students(q: str = "", status: str = "", department: str = "", section: str = "",
                  enrollment: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                  t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    from ..models import FaceTemplate
    query = scope_students(db.query(Student), t)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Student.student_id.ilike(like), Student.full_name.ilike(like)))
    if status in ("active", "inactive"):
        query = query.filter(Student.status == status)
    if department:
        query = query.filter(Student.department == department)
    if section:
        query = query.filter(Student.section == section)
    if enrollment == "enrolled":
        query = query.filter(Student.id.in_(db.query(FaceTemplate.student_pk)))
    elif enrollment == "not_enrolled":
        query = query.filter(~Student.id.in_(db.query(FaceTemplate.student_pk)),
                             Student.biometric_consent != "declined")
    elif enrollment == "declined":
        query = query.filter(Student.biometric_consent == "declined")
    total = query.count()
    rows = query.order_by(Student.full_name).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [student_out(s) for s in rows], "total": total, "page": page, "page_size": page_size,
            "departments": [r[0] for r in scope_students(db.query(Student.department), t).distinct().order_by(Student.department)],
            "sections": [r[0] for r in scope_students(db.query(Student.section), t).distinct().order_by(Student.section)]}


@router.post("", status_code=201)
def create_student(body: StudentIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    if body.student_id.upper().startswith(config.DEMO_ID_PREFIX) != is_demo(t):
        raise HTTPException(422, f"Student IDs starting with {config.DEMO_ID_PREFIX} are reserved for the demo account."
                            if not is_demo(t) else f"In the demo, student IDs must start with {config.DEMO_ID_PREFIX}.")
    if db.query(Student).filter(func.lower(Student.student_id) == body.student_id.lower()).first():
        raise HTTPException(409, f"Student ID {body.student_id} already exists.")
    s = Student(**body.model_dump())
    db.add(s)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Student ID {body.student_id} already exists.")
    audit(db, t.id, "student_create", "student", s.id, student_id=s.student_id)
    db.commit()
    return student_out(s)


@router.get("/{pk}")
def get_student(pk: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _get(db, pk)
    from ..models import Attendance, ClassCourse, class_students
    classes = [{"id": c.id, "code": c.code, "name": c.name, "section": c.section}
               for c in db.query(ClassCourse).join(class_students, class_students.c.class_id == ClassCourse.id)
               .filter(class_students.c.student_pk == pk).all()]
    out = student_out(s)
    out["classes"] = classes
    out["attendance_total"] = db.query(Attendance).filter(Attendance.student_pk == pk).count()
    return out


@router.put("/{pk}")
def update_student(pk: int, body: StudentIn, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _get(db, pk)
    dup = db.query(Student).filter(func.lower(Student.student_id) == body.student_id.lower(), Student.id != pk).first()
    if dup:
        raise HTTPException(409, f"Student ID {body.student_id} already exists.")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    audit(db, t.id, "student_update", "student", s.id)
    db.commit()
    return student_out(s)


@router.post("/{pk}/deactivate")
def deactivate(pk: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _get(db, pk)
    s.status = "inactive"
    audit(db, t.id, "student_deactivate", "student", s.id)
    db.commit()
    face_service.invalidate_gallery()  # deactivated students are no longer matched
    return student_out(s)


@router.post("/{pk}/activate")
def activate(pk: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _get(db, pk)
    s.status = "active"
    audit(db, t.id, "student_activate", "student", s.id)
    db.commit()
    face_service.invalidate_gallery()
    return student_out(s)


@router.delete("/{pk}/template")
def delete_template(pk: int, t: Teacher = Depends(current_teacher), db: Session = Depends(get_db)):
    s = _get(db, pk)
    if not s.template:
        raise HTTPException(404, "This student has no stored face template.")
    db.delete(s.template)
    s.biometric_consent = "withdrawn"
    audit(db, t.id, "biometric_delete", "student", s.id)
    db.commit()
    face_service.invalidate_gallery()
    return student_out(s)


@router.post("/{pk}/consent")
def record_consent_decline(pk: int, body: ConsentIn, t: Teacher = Depends(current_teacher),
                           db: Session = Depends(get_db)):
    """Records that the student declined biometric enrollment (manual attendance is used instead)."""
    s = _get(db, pk)
    if s.template:
        raise HTTPException(409, "Delete the existing face template first.")
    s.biometric_consent = "declined"
    audit(db, t.id, "consent_declined", "student", s.id)
    db.commit()
    return student_out(s)
