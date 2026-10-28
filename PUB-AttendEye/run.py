"""Launch PUB AttendEye locally:  python run.py"""
import os

import uvicorn

from app import config
from app.database import SessionLocal, init_db
from app.models import Teacher


def main():
    init_db()
    with SessionLocal() as db:
        if db.query(Teacher).count() == 0:
            print("\nNo teacher account yet: the browser will show the first-run setup screen.\n")
    if not config.DETECTOR_MODEL.exists() or not config.RECOGNIZER_MODEL.exists():
        print("\n[warning] Face models are missing. Run: python scripts/download_models.py\n"
              "          The app will start, but recognition and enrollment will report 'service unavailable'.\n")
    host = os.getenv("ATTENDEYE_HOST", "127.0.0.1")
    port = int(os.getenv("ATTENDEYE_PORT", "8000"))
    print(f"PUB AttendEye running at http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
