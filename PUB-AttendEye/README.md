# PUB AttendEye

*Smarter Attendance. Safer Verification. Greater Trust.*

Computer-vision classroom attendance for university teachers. Runs entirely on one Windows laptop: FastAPI + SQLite + OpenCV (YuNet face detection, SFace face recognition) with a plain HTML/CSS/JavaScript front end. No cloud server is needed.

> **Status: prototype.** It has automated tests and a browser walkthrough, but it has **not** had a security or privacy audit and has not been measured on your classroom. Do not describe it as production-ready. Recognition thresholds are generic defaults; use **System Evaluation** to measure your own setup.

## Quick start: double-click install (no terminal, no build)

1. Right-click the downloaded `.zip` > **Extract All...**, then double-click **Install PUB AttendEye**. A progress window sets everything up (needs internet once, about 150 MB, no admin rights).
2. Open the **PUB AttendEye** icon on your Desktop or Start menu. It opens in its own window.
3. First time: create the administrator account on the welcome screen. Later you can **Create new account** or **Try the demo account** from the sign-in screen.

The scripts in `installer\` have not been run on Windows by their author; the first install on a real PC is the test (errors are saved to `%LOCALAPPDATA%\PUB-AttendEye\logs\install.log`). For a single `.exe` setup file instead, use the build route below.

## Accounts and the demo

- **Create new account** (sign-in screen) makes a *teacher* account, never an administrator. It works only on the computer that runs the app, and only after the first administrator exists. Turn it off with the environment variable `ATTENDEYE_ALLOW_SIGNUP=0`. Administrators can still add accounts in Settings.
- **Try the demo account** opens a sandbox teacher (`demo`) with a fictional class (DEMO101), 8 sample students, 3 past sessions and one active session. It has no password (it can be entered only with that button, only from this computer), its data is hidden from all real accounts, and real accounts cannot use `DEMO-` student IDs. Sample students have no face templates, so camera recognition needs a consenting volunteer to enroll. Turn the demo off with `ATTENDEYE_ENABLE_DEMO=0`.
- Opening the demo before creating the first account does not count as setup; the welcome screen still appears afterwards.

## Build a Windows .exe installer (optional)

Build the installer once (see `packaging/INSTALL.md`), then on any Windows 10/11 PC:

1. Run `PUB-AttendEye-Setup-1.0.0.exe` (no admin rights needed; it needs no Python and no internet).
2. Open **PUB AttendEye** from the desktop or Start menu. It opens in its own window.
3. First launch: create your administrator account on the welcome screen, then allow the camera when asked.

Your data lives in `%LOCALAPPDATA%\PUB AttendEye\` (database, encryption keys, logs); uninstalling asks before deleting it. Edge or Chrome must be installed (Edge comes with Windows).

## Developer setup (Windows, VS Code)

1. Install Python 3.10+ from python.org (tick "Add python.exe to PATH").
2. Open this folder in VS Code, then a terminal (Terminal > New Terminal):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python scripts\download_models.py   # downloads the two ONNX models (~39 MB) into models\
python run.py                       # or: python desktop.py  (app window, same as the installed app)
```

3. Open **http://localhost:8000** in Chrome or Edge; the first visit shows the admin-account setup screen. Allow camera access when asked (camera works on `localhost`).

Typical first run: Students > Add student; Classes & Sessions > New class, Manage roster, New session; Face Enrollment (with consent); Live Attendance > Start Attendance.

## How it works

- The browser captures webcam frames and sends JPEGs to the backend; detection, quality checks and recognition run server-side in OpenCV. If the models are missing, the app says so and never fakes a match.
- **AttendEye TrustScore** is the decision policy. The similarity is cosine similarity between face embeddings (-1 to 1), *not* a probability.
  - Accepted Match: above the accept threshold, with a margin over the runner-up, confirmed over consecutive frames.
  - Needs Teacher Review: plausible but uncertain; goes to the Review Queue and creates **no** attendance until a teacher confirms.
  - Unknown Identity, Poor Image Quality, Duplicate Attendance, Session Not Active and Processing Error never create attendance.
- A unique constraint on (student, session) prevents duplicate records. Confirming a review re-checks the session, the student and the duplicate rule.
- Students who do not consent use **manual check-in** (Live Attendance page).

## Privacy and security

- Enrollment requires recorded consent; only an averaged, **Fernet-encrypted** 128-d template is stored (key in `data/`). No photos are kept; review thumbnails exist only while a case is pending.
- Templates are never returned by the API. Delete one per student, or all (admin), from Students/Settings.
- Passwords are hashed with scrypt; sessions use signed HttpOnly SameSite=Strict cookies; state-changing calls need a CSRF header; login lockout after repeated failures.
- Threshold/quality/privacy settings are admin-only. Corrections and removals are audit-logged. CSV exports neutralise spreadsheet formulas.
- `data/` (database, keys) and `models/*.onnx` are git-ignored. **Never commit `data/`.**

## Layout

```
app/          FastAPI: routers/ (API), services/ (business logic), cv/ (vision), models.py (SQLAlchemy), security.py
static/       index.html, css/app.css, js/ (api, ui, charts, camera, pages/*)
scripts/      create_teacher.py, download_models.py
tests/        pytest suite
run.py        launcher
```

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

## Verification status (what has actually been run)

- **Automated:** `python -m pytest -q` runs 44 tests (login/lockout/access control, students, consent, sessions, duplicates incl. concurrent requests, unknown/uncertain/duplicate recognition with a mocked camera and model, review decisions, history queries, CSV formula protection, report definitions, evaluation maths). Mutation checks confirmed the tests fail when the unknown-face rule or the consecutive-frame rule is broken.
- **Browser walkthrough:** a 50-step Playwright run of the whole workflow (login to CSV export) using Chromium's fake webcam fed with one public-domain photo and the real YuNet/SFace models.
- **NOT yet done:** testing with a real webcam and several real people, measured accuracy on a real dataset, a security/privacy audit. See `docs/MANUAL_TESTS.md`. Do not quote accuracy numbers until System Evaluation contains your own samples.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Model file missing` / "Recognition offline" badge | `python scripts\download_models.py` (needs internet once), restart |
| Camera permission message | Click the camera icon in the address bar, allow, press Start Camera. Use `http://localhost:8000`, not an IP address |
| Camera in use | Close Teams/Zoom/other tabs using the webcam |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process Bypass` |
| Port 8000 busy | `set ATTENDEYE_PORT=8001` then `python run.py` |
| No teacher account | `python scripts\create_teacher.py --admin` |
| Forgot password | Another admin can reset it in Settings; or run `python scripts\create_teacher.py --admin` (set `ATTENDEYE_DATA_DIR` to the app's data folder for the installed app) |
| Installed app will not open | Check `%LOCALAPPDATA%\PUB AttendEye\logs\attendeye.log` |

## More documentation

`docs/ARCHITECTURE.md` (layers, ER diagram, similarity vs probability) - `docs/API.md` (generated; `python scripts/gen_api_docs.py`) - `docs/MANUAL_TESTS.md` - `docs/DEMO.md` (script and judge Q&A) - `docs/THIRD_PARTY.md` (model licences) - `docs/TEAM.md`.

## Known limits

- Face recognition can be wrong; lighting, glasses, masks and camera quality matter. Keep the teacher in the loop.
- No liveness/anti-spoofing: a photo of a student may fool the system.
- Single-machine SQLite; no HTTPS (use only on localhost / a trusted network).
