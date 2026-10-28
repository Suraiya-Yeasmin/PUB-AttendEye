"""Centralised configuration. Everything path- or environment-dependent lives here."""
import os
import sys
from pathlib import Path

# Frozen = running from the installed desktop app (PyInstaller). Bundled read-only resources (static files,
# face models) live next to the code; the teacher's data must live in a per-user writable folder instead.
FROZEN = bool(getattr(sys, "frozen", False))
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _default_data_dir() -> Path:
    if not FROZEN:
        return BASE_DIR / "data"  # developer checkout: keep data beside the code, as before
    root = os.getenv("LOCALAPPDATA") or os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / "PUB AttendEye" / "data"


DATA_DIR = Path(os.getenv("ATTENDEYE_DATA_DIR", _default_data_dir()))
# Logs and the app-window browser profile (not patient/student data) sit beside data/ in the installed app.
STATE_DIR = DATA_DIR.parent if FROZEN else DATA_DIR / "_runtime"
MODEL_DIR = Path(os.getenv("ATTENDEYE_MODEL_DIR", BASE_DIR / "models"))
STATIC_DIR = BASE_DIR / "static"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv("ATTENDEYE_DB_URL", f"sqlite:///{(DATA_DIR / 'attendeye.db').as_posix()}")

DETECTOR_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"
MODEL_INFO = {
    "detector": "YuNet (face_detection_yunet_2023mar) via OpenCV FaceDetectorYN",
    "recognizer": "SFace (face_recognition_sface_2021dec) via OpenCV FaceRecognizerSF, 128-d embedding",
}

# Login-screen conveniences. Both are honoured only for requests coming from this computer (loopback).
ALLOW_SIGNUP = os.getenv("ATTENDEYE_ALLOW_SIGNUP", "1").lower() not in ("0", "false", "no", "off")
ENABLE_DEMO = os.getenv("ATTENDEYE_ENABLE_DEMO", "1").lower() not in ("0", "false", "no", "off")
DEMO_USERNAME = "demo"
DEMO_ID_PREFIX = "DEMO-"

SESSION_COOKIE = "attendeye_session"
SESSION_HOURS = 8
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "AttendEye"
MAX_FRAME_BYTES = 2_000_000
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 10
ENROLL_SAMPLES = 5
ENROLL_DRAFT_TTL_SECONDS = 600

APP_NAME = "PUB AttendEye"
APP_VERSION = "1.0.0"
TAGLINE = "Smarter Attendance. Safer Verification. Greater Trust."
