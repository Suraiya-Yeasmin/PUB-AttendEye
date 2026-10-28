"""Create a teacher/administrator account (passwords are never stored in code).

    python scripts/create_teacher.py                       # interactive
    python scripts/create_teacher.py --admin               # make the account an administrator
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Teacher  # noqa: E402
from app.security import hash_password  # noqa: E402


def create(username, email, full_name, password, admin=False):
    init_db()
    with SessionLocal() as db:
        if db.query(Teacher).filter((Teacher.username == username.lower()) | (Teacher.email == email.lower())).first():
            raise SystemExit("That username or email already exists.")
        db.add(Teacher(username=username.lower(), email=email.lower(), full_name=full_name,
                       password_hash=hash_password(password), role="admin" if admin else "teacher"))
        db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin", action="store_true")
    ap.add_argument("--username"); ap.add_argument("--email"); ap.add_argument("--name")
    a = ap.parse_args()
    username = a.username or input("Username: ").strip()
    email = a.email or input("Email: ").strip()
    name = a.name or input("Full name: ").strip()
    pw = os.environ.get("ATTENDEYE_NEW_PASSWORD")  # non-interactive option for automation
    if not pw:
        pw = getpass.getpass("Password (min 8 chars): ")
        if pw != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords do not match.")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    create(username, email, name, pw, a.admin)
    print(f"Account '{username}' created ({'administrator' if a.admin else 'teacher'}).")


if __name__ == "__main__":
    main()
