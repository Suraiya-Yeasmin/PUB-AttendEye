# Demo kit

Use only what you have run on your own laptop. Rehearse twice. Keep a backup screen recording made from a *real* run with a *real* webcam and say so.

## 5-minute outline
1. **Problem (30 s):** paper/roll-call attendance is slow, proxies happen, and naive face recognition silently marks the wrong person.
2. **Idea (30 s):** AttendEye proposes a candidate, explains its certainty, and the teacher stays in control of anything uncertain.
3. **Live demo (3 min):** see script.
4. **Evidence and honesty (45 s):** System Evaluation page: samples, false accepts/rejects, review rate, latency, "what-if" thresholds, limitations.
5. **Responsible use (15 s):** consent first, encrypted templates, deletion, manual alternative.

## Live demo script (check each step works on your machine first)
| # | Do | Say | Expect |
|---|---|---|---|
| 1 | Sign in, show Dashboard | "Every number is read from the database." | Real counts, empty states if new |
| 2 | Students > add a consenting teammate | "No face data until consent." | Student appears |
| 3 | Face Enrollment: tick consent, enroll | "Five samples averaged into one encrypted template; no photo is kept." | "Enrollment completed successfully" |
| 4 | Classes: class, roster, session | "Attendance can only be recorded in an active session." | Session Scheduled |
| 5 | Live Attendance > Start Attendance | "The box is a candidate, not a decision." | Pending, then Attendance recorded |
| 6 | Stay in view | "Duplicates are blocked by the database too." | Duplicate, still one record |
| 7 | An unenrolled teammate steps in | "Unknown stays unknown." | Unknown, no record |
| 8 | Turn head / move back to get an uncertain result (do not fake it) | "Uncertain goes to the teacher with a reason." | Review Queue case |
| 9 | Review Queue: confirm | "Confirm re-checks session, student and duplicates." | Record created, method "Face + teacher review" |
| 10 | Reports: export CSV, open it | "Pending review is not counted as absent or present." | Real file |
| 11 | System Evaluation | read the numbers as they are; say "small sample" if it is | No invented figures |

If a step does not behave (e.g. no uncertain result appears), say so and move on; never stage it.

## Likely judge questions, honest answers
- **How accurate is it?** "We report measured counts from our own captures on the Evaluation page (N samples, conditions listed). That is not a general accuracy claim; the sample is small and from our team." Give the real N.
- **Is the score a probability?** "No. It is cosine similarity between embeddings. We never show it as a percentage of certainty. Thresholds are operating points we can tune with the what-if table."
- **Can a photo fool it?** "Yes. There is no liveness or anti-spoofing. The teacher review and in-room supervision are the mitigation; liveness is future work."
- **What about bias and lighting?** "Face recognition error rates vary with lighting, camera, pose and demographics. We did not measure demographic differences. Uncertain cases go to a human, and manual attendance is always available."
- **Privacy?** "Consent is recorded before enrollment; templates are 128 numbers, encrypted at rest, never sent by the API; deletable per student or all; no photos kept except a review thumbnail until the teacher decides. Not security-audited; we do not claim legal compliance."
- **Does it scale?** "It is built for one classroom on one laptop with SQLite. Moving to PostgreSQL, HTTPS and a server-side camera pipeline would be needed for a campus."
- **What is new?** "The explainable decision policy: every non-accept has a reason, uncertain cases need a human, and reports separate confirmed, pending and absent."
- **What did you not do?** Liveness, multi-camera, mobile app, integration with the university system, demographic testing, security audit.
