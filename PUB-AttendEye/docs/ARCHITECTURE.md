# Architecture

```
Browser (HTML/CSS/JS modules)  --JSON/JPEG over HTTP-->  FastAPI routers (app/routers)
   webcam via getUserMedia                                   |  validation, authz, HTTP codes
                                                             v
                                            services (app/services): attendance, recognition, trustscore, settings
                                                             |
                               cv/service.py (OpenCV YuNet + SFace)      SQLAlchemy models -> SQLite (data/attendeye.db)
```

- **Frontend never touches SQLite**; it only calls `/api/*` (see `API.md`).
- **One place creates attendance:** `services/attendance.py::record_attendance` (used by face, review-confirm and manual). It re-checks session active + student active; the `UNIQUE(student_pk, session_id)` constraint is the final duplicate guard, also under concurrent requests (tested).
- **Decision pipeline (live frame):** detect (YuNet) -> quality gate -> align + embed (SFace) -> cosine match against encrypted templates -> TrustScore policy -> session rules (roster, duplicate, consecutive frames) -> record / open review case / ignore.

## Database ER diagram

```mermaid
erDiagram
    TEACHERS ||--o{ CLASSES : teaches
    CLASSES ||--o{ SESSIONS : has
    CLASSES }o--o{ STUDENTS : roster
    STUDENTS ||--o| FACE_TEMPLATES : "has (encrypted)"
    SESSIONS ||--o{ ATTENDANCE : records
    STUDENTS ||--o{ ATTENDANCE : "UNIQUE(student,session)"
    SESSIONS ||--o{ RECOGNITION_EVENTS : logs
    STUDENTS |o--o{ RECOGNITION_EVENTS : candidate
    RECOGNITION_EVENTS ||--o{ REVIEW_EVENTS : "teacher decisions"
    TEACHERS ||--o{ REVIEW_EVENTS : makes
    TEACHERS ||--o{ AUDIT_LOGS : performs
    TEACHERS { int id PK  string username  string role  string password_hash }
    STUDENTS { int id PK  string student_id UK  string full_name  string biometric_consent  string status }
    FACE_TEMPLATES { int id PK  int student_pk FK  blob embedding_enc  datetime consent_recorded_at }
    CLASSES { int id PK  string code  string section  int teacher_id FK }
    SESSIONS { int id PK  int class_id FK  date session_date  string status }
    ATTENDANCE { int id PK  int session_id FK  int student_pk FK  string method  string status  string review_status  float similarity  bool corrected }
    RECOGNITION_EVENTS { int id PK  int session_id FK  int student_pk FK  float similarity  string decision  string reason  string review_status }
    REVIEW_EVENTS { int id PK  int recognition_event_id FK  int teacher_id FK  string action }
    AUDIT_LOGS { int id PK  int teacher_id FK  string action  string entity_type  datetime timestamp }
    SETTINGS { string key PK  string value }
    EVALUATION_SAMPLES { int id PK  int truth_student_pk  int predicted_student_pk  float similarity  string decision }
```

## Reading the numbers (important for judges)

| Term | Meaning here |
|---|---|
| **Similarity score** | Cosine similarity of two 128-d SFace embeddings (-1..1). A distance-style score. **Not** a probability. |
| **Calibrated probability** | "If the system says 90 %, it is right 90 % of the time." AttendEye does **not** produce this; we show no confidence percentages. |
| **Measured accuracy** | False-accept / false-reject counts from labelled captures on *this* installation (System Evaluation page). Only valid for the conditions and people tested. |

TrustScore describes how reliable one *recognition decision* is. It says nothing about a person.

## Schema changes
`init_db()` uses `create_all`, which creates missing tables but does not alter existing ones. This version added **no** columns. If a future change needs one, take a copy of `data/attendeye.db`, add the column with `ALTER TABLE ... ADD COLUMN`, and run the tests before deleting the copy.
