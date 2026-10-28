"""Pydantic request bodies with input validation."""
import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _clean(v: str) -> str:
    return re.sub(r"\s+", " ", v).strip()


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254)

    @field_validator("full_name")
    @classmethod
    def _n(cls, v): return _clean(v)

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        if not _EMAIL.match(v.strip()):
            raise ValueError("Enter a valid email address")
        return v.strip().lower()


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class TeacherCreateIn(ProfileIn):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(default="teacher", pattern="^(teacher|admin)$")


class StudentIn(BaseModel):
    student_id: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9._/-]+$")
    full_name: str = Field(min_length=2, max_length=120)
    department: str = Field(min_length=2, max_length=80)
    section: str = Field(min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("full_name", "department", "section")
    @classmethod
    def _c(cls, v): return _clean(v)

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        if v in (None, ""):
            return None
        if not _EMAIL.match(v.strip()):
            raise ValueError("Enter a valid email address")
        return v.strip().lower()


class ConsentIn(BaseModel):
    consent: str = Field(pattern="^(declined)$")


class EnrollStartIn(BaseModel):
    student_pk: int
    consent: bool
    replace: bool = False


class ClassIn(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9 ._/-]+$")
    name: str = Field(min_length=2, max_length=160)
    section: str = Field(min_length=1, max_length=32)
    department: str | None = Field(default=None, max_length=80)
    teacher_id: int | None = None

    @field_validator("code", "name", "section", "department")
    @classmethod
    def _c(cls, v): return _clean(v) if v else v


class RosterIn(BaseModel):
    student_pks: list[int] = Field(max_length=2000)


class RosterBySectionIn(BaseModel):
    section: str = Field(min_length=1, max_length=32)
    department: str | None = None


class SessionIn(BaseModel):
    class_id: int
    session_date: date
    start_time: str
    end_time: str

    @field_validator("start_time", "end_time")
    @classmethod
    def _t(cls, v):
        if not _TIME.match(v):
            raise ValueError("Use HH:MM (24-hour) time")
        return v


class ManualAttendanceIn(BaseModel):
    session_id: int
    student_pk: int
    status: str = Field(default="present", pattern="^(present|late|excused)$")
    note: str | None = Field(default=None, max_length=300)


class CorrectionIn(BaseModel):
    status: str = Field(pattern="^(present|late|excused)$")
    note: str = Field(min_length=3, max_length=300)


class RemovalIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ReviewDecisionIn(BaseModel):
    action: str = Field(pattern="^(confirm|reject|unknown|keep_pending)$")
    note: str | None = Field(default=None, max_length=300)


class SettingsIn(BaseModel):
    values: dict[str, int | float | str | bool]


class PurgeIn(BaseModel):
    confirm: str
