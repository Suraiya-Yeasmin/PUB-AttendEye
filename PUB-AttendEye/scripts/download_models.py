"""Downloads the two pretrained OpenCV Zoo models used by PUB AttendEye and verifies their SHA-256.

    python scripts/download_models.py
"""
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

MODEL_DIR = Path(os.getenv("ATTENDEYE_MODEL_DIR") or Path(__file__).resolve().parent.parent / "models")
BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": (
        f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in MODELS.items():
        dest = MODEL_DIR / name
        if dest.exists() and sha256(dest) == digest:
            print(f"[ok]   {name} already present")
            continue
        print(f"[get]  {name} ...")
        urllib.request.urlretrieve(url, dest)
        if sha256(dest) != digest:
            dest.unlink(missing_ok=True)
            print(f"[FAIL] checksum mismatch for {name}", file=sys.stderr)
            return 1
        print(f"[ok]   {name} verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
