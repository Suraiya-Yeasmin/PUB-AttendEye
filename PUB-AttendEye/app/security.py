"""Password hashing (scrypt), signed session tokens (HMAC-SHA256) and template encryption (Fernet)."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.fernet import Fernet

from . import config


def _load_or_create_key(name: str, factory) -> bytes:
    path = config.DATA_DIR / name
    if path.exists():
        return path.read_bytes().strip()
    key = factory()
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


_SIGN_KEY = _load_or_create_key("session_secret.key", lambda: base64.urlsafe_b64encode(secrets.token_bytes(48)))
_fernet = Fernet(_load_or_create_key("template_encryption.key", Fernet.generate_key))

# ---- passwords -------------------------------------------------------------
_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r),
                              p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


DUMMY_HASH = hash_password(secrets.token_urlsafe(12))  # equalises timing for unknown usernames

# ---- session tokens --------------------------------------------------------


def make_token(teacher_id: int, epoch: int) -> str:
    payload = {"t": teacher_id, "e": epoch, "x": int(time.time()) + config.SESSION_HOURS * 3600}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_SIGN_KEY, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_token(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    good = hmac.new(_SIGN_KEY, body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:
        return None
    return payload if payload.get("x", 0) > time.time() else None


# ---- template encryption ---------------------------------------------------
def encrypt_bytes(raw: bytes) -> bytes:
    return _fernet.encrypt(raw)


def decrypt_bytes(blob: bytes) -> bytes:
    return _fernet.decrypt(blob)
