"""PUB AttendEye desktop launcher: double-click the app, no terminal needed.

Starts the local server on 127.0.0.1, opens it in its own app-style window (Microsoft Edge or Google Chrome in
"app mode": no tabs, no address bar), and shuts the server down when that window is closed.

    python desktop.py                 # same as the installed app
    python desktop.py --no-window     # server only (tests / headless)
    python desktop.py --port 9000
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# --- Must run before anything else: a windowed (no-console) build has no stdout/stderr at all. ---------------
from app import config  # noqa: E402  (config has no side effects beyond creating DATA_DIR)

LOG_DIR = config.STATE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "attendeye.log"
if config.FROZEN or sys.stdout is None or sys.stderr is None:
    _stream = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _stream
_handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
log = logging.getLogger("attendeye.desktop")

DEFAULT_PORT = 8765
HOST = "127.0.0.1"


def message_box(title: str, text: str, error: bool = False) -> None:
    """Native dialog on Windows; plain print elsewhere."""
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)  # type: ignore[attr-defined]
    else:
        print(f"{title}: {text}", file=sys.__stderr__ or sys.stderr)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) != 0


def is_attendeye(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=1.5) as r:
            return b'"app":"PUB AttendEye"' in r.read().replace(b" ", b"")
    except (urllib.error.URLError, OSError, ValueError):
        return False


def pick_port(preferred: int) -> tuple[int, bool]:
    """Returns (port, already_running). Prefers a stable port so the camera permission is remembered."""
    if is_attendeye(preferred):
        return preferred, True
    for p in range(preferred, preferred + 20):
        if port_free(p):
            return p, False
    raise RuntimeError(f"No free port found between {preferred} and {preferred + 19}.")


def find_browsers() -> list[Path]:
    """Edge ships with Windows 10/11, so it is tried first; Chrome is the fallback."""
    out: list[Path] = []
    if os.name == "nt":
        roots = [os.getenv(k) for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        rels = ["Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"]
        for rel in rels:
            for root in filter(None, roots):
                p = Path(root) / rel
                if p.exists():
                    out.append(p)
    else:
        for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
            p = shutil.which(name)
            if p:
                out.append(Path(p))
    return out


def open_window(url: str) -> bool:
    """Open the app window and block until it is closed. Returns False if no app window could be opened."""
    profile = config.STATE_DIR / "browser-profile"  # own profile: separate process, remembers camera consent
    for exe in find_browsers():
        cmd = [str(exe), f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
               "--window-size=1366,860", "--disable-sync", "--disable-features=Translate,msEdgeSidebarV2"]
        started = time.monotonic()
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
        except OSError:
            log.exception("Could not start %s", exe)
            continue
        if time.monotonic() - started > 3:
            return True
        log.warning("%s exited immediately; trying the next browser", exe.name)
    return False


class Server:
    def __init__(self, port: int):
        import uvicorn
        from app.main import app  # imported late so the log file is already set up
        self.port = port
        cfg = uvicorn.Config(app, host=HOST, port=port, log_config=None, access_log=False,
                             http="h11", ws="none", lifespan="on")
        self.server = uvicorn.Server(cfg)
        self.thread = threading.Thread(target=self.server.run, name="uvicorn", daemon=True)

    def start(self, timeout: float = 30.0) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.started:
                return
            if not self.thread.is_alive():
                break
            time.sleep(0.1)
        raise RuntimeError("The local server did not start. See the log file for details.")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def main() -> int:
    ap = argparse.ArgumentParser(description="PUB AttendEye desktop launcher")
    ap.add_argument("--no-window", action="store_true", help="run the server only")
    ap.add_argument("--port", type=int, default=int(os.getenv("ATTENDEYE_PORT", DEFAULT_PORT)))
    args = ap.parse_args()

    try:
        port, running = pick_port(args.port)
    except RuntimeError as e:
        message_box(config.APP_NAME, str(e), error=True)
        return 1
    url = f"http://{HOST}:{port}/"

    if running:  # second launch: just bring up another window on the existing server
        log.info("Server already running on %s; opening a window only", port)
        if not args.no_window and not open_window(url):
            webbrowser.open(url)
        return 0

    log.info("%s %s starting (frozen=%s, data=%s)", config.APP_NAME, config.APP_VERSION, config.FROZEN, config.DATA_DIR)
    try:
        server = Server(port)
        server.start()
    except Exception as e:  # noqa: BLE001
        log.exception("Startup failed")
        message_box(config.APP_NAME, f"PUB AttendEye could not start.\n\n{e}\n\nLog file:\n{LOG_FILE}", error=True)
        return 1

    if args.no_window:
        print(f"PUB AttendEye serving on {url} (Ctrl+C to stop)", flush=True)
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        stop.wait()
    elif not open_window(url):
        # No Edge/Chrome app window available: use the default browser and keep the server alive until dismissed.
        log.warning("No Edge/Chrome found; falling back to the default browser")
        webbrowser.open(url)
        message_box(config.APP_NAME, "PUB AttendEye is running in your web browser.\n\n"
                                     "Leave this message open while you take attendance. "
                                     "Click OK when you are finished to stop the app.")
    server.stop()
    log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
