"""Computer-vision service: face detection (YuNet), quality checks, embedding extraction (SFace)
and gallery matching. Thread-safe; OpenCV DNN objects are guarded by a lock.

No result in this module is ever simulated: if the models cannot be loaded, every call raises
CVUnavailable and the API reports HTTP 503.
"""
import threading
import time

import cv2
import numpy as np

from .. import config


class CVUnavailable(RuntimeError):
    pass


QUALITY_MESSAGES = {
    "too_small": "Face is too small or too far from the camera. Move closer.",
    "blurry": "Image is blurry. Hold still and improve focus.",
    "too_dark": "Lighting is too dark. Face a light source.",
    "too_bright": "Face is over-exposed. Reduce direct light.",
    "turned": "Face is turned away. Look towards the camera.",
    "tilted": "Head is tilted. Keep your head upright.",
    "cut_off": "Face is partly outside the frame.",
    "low_detection": "Face detection confidence is low.",
}


class FaceService:
    def __init__(self):
        self._lock = threading.Lock()
        self._det = None
        self._rec = None
        self._error: str | None = None
        self._last_try = 0.0
        self._gallery = None
        self._gallery_dirty = True

    # ---- model lifecycle --------------------------------------------------
    def _ensure(self):
        if self._det is not None and self._rec is not None:
            return
        if time.time() - self._last_try < 2:  # avoid hammering the disk
            raise CVUnavailable(self._error or "Recognition models not loaded")
        self._last_try = time.time()
        try:
            for p in (config.DETECTOR_MODEL, config.RECOGNIZER_MODEL):
                if not p.exists():
                    raise FileNotFoundError(f"Model file missing: {p.name}. Run: python scripts/download_models.py")
            if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
                raise RuntimeError("OpenCV build lacks FaceDetectorYN/FaceRecognizerSF (need opencv-python >= 4.8)")
            det = cv2.FaceDetectorYN.create(str(config.DETECTOR_MODEL), "", (320, 320), 0.8, 0.3, 500)
            rec = cv2.FaceRecognizerSF.create(str(config.RECOGNIZER_MODEL), "")
            self._det, self._rec, self._error = det, rec, None
        except Exception as e:  # noqa: BLE001
            self._det = self._rec = None
            self._error = str(e)
            raise CVUnavailable(self._error)

    def status(self) -> dict:
        try:
            self._ensure()
            return {"available": True, "error": None, "opencv": cv2.__version__, **config.MODEL_INFO}
        except CVUnavailable as e:
            return {"available": False, "error": str(e), "opencv": cv2.__version__, **config.MODEL_INFO}

    # ---- image helpers ----------------------------------------------------
    @staticmethod
    def decode(data: bytes, max_side: int = 960):
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image (expected JPEG or PNG).")
        h, w = img.shape[:2]
        scale = max_side / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    # ---- detection / quality / embedding ---------------------------------
    def detect(self, img) -> list[np.ndarray]:
        self._ensure()
        h, w = img.shape[:2]
        with self._lock:
            self._det.setInputSize((w, h))
            _, faces = self._det.detect(img)
        if faces is None:
            return []
        return sorted(list(faces), key=lambda f: -(f[2] * f[3]))

    def assess_quality(self, img, face, s: dict) -> dict:
        """Heuristic capture-quality checks. Thresholds come from the settings table."""
        self._ensure()
        h, w = img.shape[:2]
        x, y, fw, fh = face[:4]
        with self._lock:
            aligned = self._rec.alignCrop(img, face)
        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        bright = float(gray.mean())
        re_, le_, nose = face[4:6], face[6:8], face[8:10]
        eye_dx = float(le_[0] - re_[0])
        eye_dist = max(abs(eye_dx), 1.0)
        yaw = float((nose[0] - (re_[0] + le_[0]) / 2) / eye_dist)
        roll = float(np.degrees(np.arctan2(le_[1] - re_[1], eye_dx if eye_dx else 1.0)))
        margin = 2
        inside = x >= margin and y >= margin and x + fw <= w - margin and y + fh <= h - margin
        det_score = float(face[14])
        # Face width is measured relative to a 640-px-wide frame so the rule is resolution independent.
        face_px = float(fw * 640.0 / w)
        issues = []
        if face_px < s["min_face_px"]:
            issues.append("too_small")
        if sharp < s["min_sharpness"]:
            issues.append("blurry")
        if bright < s["min_brightness"]:
            issues.append("too_dark")
        if bright > s["max_brightness"]:
            issues.append("too_bright")
        if abs(yaw) > s["max_yaw"]:
            issues.append("turned")
        if abs(roll) > 30:
            issues.append("tilted")
        if not inside:
            issues.append("cut_off")
        if det_score < 0.85:
            issues.append("low_detection")
        return {
            "ok": not issues,
            "issues": issues,
            "messages": [QUALITY_MESSAGES[i] for i in issues],
            "metrics": {"face_px": round(face_px), "sharpness": round(sharp, 1), "brightness": round(bright),
                        "head_turn": round(yaw, 2), "head_tilt_deg": round(roll, 1),
                        "detector_score": round(det_score, 3)},
        }

    def embed(self, img, face) -> np.ndarray:
        self._ensure()
        with self._lock:
            aligned = self._rec.alignCrop(img, face)
            feat = self._rec.feature(aligned)
        v = np.asarray(feat, dtype=np.float32).reshape(-1)
        n = float(np.linalg.norm(v))
        if n == 0:
            raise CVUnavailable("Empty embedding returned by recognizer")
        return v / n

    @staticmethod
    def thumbnail(img, face, size: int = 112) -> bytes:
        x, y, w, h = [int(v) for v in face[:4]]
        pad = int(0.25 * max(w, h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        crop = img[y0:min(img.shape[0], y + h + pad), x0:min(img.shape[1], x + w + pad)]
        if crop.size == 0:
            return b""
        crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else b""

    # ---- gallery ----------------------------------------------------------
    def invalidate_gallery(self):
        self._gallery_dirty = True

    def gallery(self, db):
        """Returns (student_pks list, matrix NxD) of decrypted, normalised templates of active students."""
        if not self._gallery_dirty and self._gallery is not None:
            return self._gallery
        from ..models import FaceTemplate, Student
        from ..security import decrypt_bytes
        rows = (db.query(FaceTemplate).join(Student, Student.id == FaceTemplate.student_pk)
                .filter(Student.status == "active").all())
        ids, vecs = [], []
        for r in rows:
            try:
                v = np.frombuffer(decrypt_bytes(r.embedding_enc), dtype=np.float32)
            except Exception:  # corrupted or wrong key: skip, never crash recognition
                continue
            ids.append(r.student_pk)
            vecs.append(v / (np.linalg.norm(v) or 1.0))
        matrix = np.vstack(vecs) if vecs else np.zeros((0, 128), dtype=np.float32)
        self._gallery = (ids, matrix)
        self._gallery_dirty = False
        return self._gallery

    @staticmethod
    def match(vec: np.ndarray, gallery) -> tuple[int | None, float | None, float | None]:
        ids, matrix = gallery
        if not ids:
            return None, None, None
        sims = matrix @ vec  # cosine similarity (both unit length)
        order = np.argsort(-sims)
        best = int(order[0])
        runner = float(sims[order[1]]) if len(order) > 1 else None
        return ids[best], float(sims[best]), runner


face_service = FaceService()
