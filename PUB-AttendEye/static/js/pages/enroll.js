import { api } from '../api.js';
import { h, setHTML, $, qs } from '../util.js';
import { icon } from '../icons.js';
import { toast, callout, empty, consentBadge, confirmDialog, withBusy } from '../ui.js';
import { Camera, describeCameraError, drawFaces, listCameras, savedCamera } from '../camera.js';

const INTERVAL_MS = 750;
const COLORS = { ok: '#0d8a77', warn: '#d98a06', bad: '#dc2626', idle: '#5b5fe0' };

export default async function render(root, ctx) {
  let students = [], student = null, camera = null, running = false, enrolling = false, timer = 0, busy = false, destroyed = false, result = null;
  const svc = await api.get('/api/recognition/status').catch((e) => ({ available: false, error: e.message }));
  const res = await api.get('/api/students?page_size=200&status=active');
  students = res.items;
  const want = ctx.params.get('student');
  student = students.find((s) => String(s.id) === want) || null;

  setHTML(root, h`
    <div class="page-head"><div><h1>Face enrollment</h1><p>Consent-based enrollment. Several samples are averaged into one encrypted template; raw photos are never stored.</p></div></div>
    ${svc.available ? '' : h`<div style="margin-bottom:16px">${callout('error', h`<b>Recognition service unavailable.</b> ${svc.error || ''} Run <code>python scripts/download_models.py</code> and restart the app. Enrollment is disabled until the models load.`)}</div>`}
    <div class="steps" id="steps"></div>
    <div class="grid g2">
      <div class="stack">
        <section class="card"><div class="card-head"><h2>1. Student</h2></div><div class="card-body">
          ${students.length ? h`<div class="field"><label for="pick">Select student</label><select class="select" id="pick"><option value="">Choose a student…</option>${students.map((s) => h`<option value="${s.id}" ${student?.id === s.id ? 'selected' : ''}>${s.full_name} (${s.student_id})</option>`)}</select></div><div id="summary" style="margin-top:14px"></div>`
            : empty({ icon: 'users', title: 'No active students', text: 'Add a student first.', action: h`<a class="btn primary" href="#/students?new=1">${icon('userplus')} Add student</a>` })}
        </div></section>
        <section class="card"><div class="card-head"><h2>2. Informed consent</h2></div><div class="card-body" id="consent"></div></section>
      </div>
      <div class="stack">
        <section class="card"><div class="card-head"><h2>3. Capture</h2><span class="small muted" id="cam-name" style="max-width:55%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span></div><div class="card-body">
          <div class="cam" id="cam"><video id="video" playsinline muted></video><canvas id="overlay"></canvas><div class="hud" id="hud"></div>
            <div class="placeholder" id="ph">${icon('camera')}<b>Camera is off</b><p class="small" style="margin-top:4px">Confirm consent, then press Start enrollment. Position your face inside the camera frame.</p></div></div>
          <div class="row" style="margin-top:14px" id="controls"></div>
          <div id="msg" style="margin-top:12px"></div>
          <div style="margin-top:14px"><div class="row spread small"><b>Enrollment progress</b><span id="prog-text">0 of 0 samples</span></div><div class="progress" style="margin-top:6px"><i id="prog" style="width:0"></i></div></div>
          <dl class="kv" id="metrics" style="margin-top:14px;grid-template-columns:150px 1fr"></dl>
        </div></section>
      </div>
    </div>`);

  const $$ = (s) => $(s, root);
  const camera_ = new Camera($$('#video'));
  camera = camera_;
  camera.onEnded = () => { stopAll('The camera was disconnected.'); };

  const consentBox = () => $$('#consent-ok')?.checked;
  function paintSteps(state = 'idle') {
    const steps = [['Student', !!student], ['Consent', !!student && consentBox()], ['Capture', state === 'done']];
    const now = steps.findIndex((s) => !s[1]);
    setHTML($$('#steps'), h`${steps.map(([t, ok], i) => h`<span class="step ${ok ? 'done' : i === now ? 'now' : ''}"><i>${ok ? '✓' : i + 1}</i>${t}</span>`)}<span class="step ${state === 'done' ? 'done' : ''}"><i>${state === 'done' ? '✓' : 4}</i>Result</span>`);
  }
  function paintSummary() {
    const el = $$('#summary'); if (!el) return;
    setHTML(el, student ? h`<dl class="kv" style="grid-template-columns:120px 1fr"><dt>Name</dt><dd>${student.full_name}</dd><dt>Student ID</dt><dd>${student.student_id}</dd><dt>Department</dt><dd>${student.department} · Sec ${student.section}</dd><dt>Biometric status</dt><dd>${consentBadge(student)}</dd></dl>` : h`<p class="hint">Select a student to continue.</p>`);
  }
  function paintConsent() {
    const el = $$('#consent'); if (!el) return;
    if (!student) { setHTML(el, h`<p class="hint">Select a student first.</p>`); return; }
    if (student.face_enrolled) {
      setHTML(el, h`${callout('info', 'This student already has a face template. Re-enrolling replaces it. The student must give fresh consent.')}<div style="height:12px"></div>${consentForm(true)}`);
    } else setHTML(el, consentForm(false));
    $$('#consent-ok')?.addEventListener('change', () => { paintSteps(); paintControls(); });
    $$('#decline')?.addEventListener('click', onDecline);
    paintSteps(); paintControls();
  }
  const consentForm = (replace) => h`<div class="callout info">${icon('shield')}<div><b>Why consent matters.</b> A face template is biometric data. It is collected only with the student's free, informed, and revocable consent. It is stored encrypted on this laptop, used only to propose attendance matches, and can be deleted at any time (Students → Remove face template).</div></div>
    <label class="check" style="margin-top:14px"><input type="checkbox" id="consent-ok"><span>${student.full_name} has been informed about what is collected, why, and how to withdraw, and <b>voluntarily consents</b> to face enrollment.</span></label>
    <div class="row" style="margin-top:14px;align-items:flex-start"><button class="btn sm" id="decline" ${student.biometric_consent === 'declined' || replace ? 'disabled' : ''}>${icon('userx', 'sm')} Student declines</button><span class="hint">Declining has no academic consequence. The teacher marks attendance manually instead (Live Attendance → Manual check-in).</span></div>`;

  function paintControls() {
    const el = $$('#controls'); const can = svc.available && student && consentBox();
    setHTML(el, running
      ? h`<button class="btn danger" id="stop">${icon('stop')} Cancel enrollment</button>`
      : h`<button class="btn primary" id="start" ${can ? '' : 'disabled'}>${icon('play')} ${student?.face_enrolled ? 'Start re-enrollment' : 'Start enrollment'}</button>${!svc.available ? h`<span class="hint">Recognition service unavailable.</span>` : !student ? h`<span class="hint">Select a student.</span>` : !consentBox() ? h`<span class="hint">Consent must be confirmed first.</span>` : ''}`);
    $$('#start')?.addEventListener('click', onStart); $$('#stop')?.addEventListener('click', () => stopAll('Enrollment cancelled. Nothing was saved.'));
  }
  function setMsg(kind, text) { setHTML($$('#msg'), text ? callout(kind, text) : ''); }
  function setProgress(c, t) { $$('#prog').style.width = `${t ? (100 * c) / t : 0}%`; $$('#prog-text').textContent = `${c} of ${t} samples`; }
  function hud(on, label) { setHTML($$('#hud'), h`<span class="chip ${on ? 'on' : 'bad'}"><i></i>${label}</span>`); }

  async function onDecline() {
    if (!(await confirmDialog({ title: 'Record that the student declined?', message: `${student.full_name} will be marked as not consenting to biometrics. Use manual check-in for them.`, confirmText: 'Record' }))) return;
    try { const s = await api.post(`/api/students/${student.id}/consent`, { consent: 'declined' }); Object.assign(student, s); paintSummary(); paintConsent(); toast('Recorded. Manual check-in is the alternative for this student.'); }
    catch (e) { toast(e.message, 'error'); }
  }

  async function onStart(e) {
    const btn = e.currentTarget; result = null;
    try {
      await withBusy(btn, async () => {
        const cams = await listCameras(); void cams;
        const label = await camera.start(savedCamera());
        $$('#cam-name').textContent = label || '';
        await api.post('/api/enrollment/start', { student_pk: student.id, consent: true, replace: !!student.face_enrolled });
      }, 'Starting…');
    } catch (ex) {
      camera.stop();
      setMsg('error', ex.status ? ex.message : describeCameraError(ex)); hud(false, 'Camera off'); return;
    }
    running = true; enrolling = true; $$('#ph').style.display = 'none'; hud(true, 'Camera live'); setProgress(0, 5);
    setMsg('info', 'Position your face inside the camera frame.'); paintControls(); paintSteps();
    timer = setInterval(tick, INTERVAL_MS);
  }

  async function tick() {
    if (busy || !running || destroyed) return; busy = true;
    try {
      const blob = await camera.capture(640, 0.85); if (!blob || !running) return;
      const r = await api.frame(`/api/enrollment/frame/${student.id}`, blob);
      if (!running) return;
      setProgress(r.count, r.target);
      const color = r.status === 'captured' || r.status === 'completed' ? COLORS.ok : r.status === 'waiting' ? COLORS.idle : r.status === 'no_face' ? COLORS.idle : r.status === 'poor_quality' ? COLORS.warn : COLORS.bad;
      drawFaces($$('#overlay'), camera.video, r.frame, r.bbox ? [{ bbox: r.bbox, color, lines: [labelFor(r.status)] }] : []);
      paintMetrics(r.quality);
      if (r.status === 'completed') {
        finish(true, r.message); student.face_enrolled = true; student.biometric_consent = 'granted'; paintSummary(); paintConsent();
      } else if (r.status === 'duplicate_face') { finish(false, r.message); }
      else setMsg(r.status === 'captured' ? 'ok' : r.status === 'waiting' ? 'info' : r.status === 'no_face' ? 'info' : 'warn', r.message);
    } catch (ex) {
      if (ex.status === 409 || ex.status === 503) { finish(false, ex.message); } else setMsg('error', ex.message);
    } finally { busy = false; }
  }
  const labelFor = (s) => ({ captured: 'Sample captured', completed: 'Enrolled', waiting: 'Hold still', no_face: '', poor_quality: 'Quality too low', multiple_faces: 'Multiple faces', inconsistent: 'Different face', duplicate_face: 'Already enrolled' }[s] || '');
  function paintMetrics(q) {
    const el = $$('#metrics'); if (!q) { return; }
    const m = q.metrics;
    setHTML(el, h`<dt>Image quality</dt><dd>${q.ok ? h`<span class="badge b-teal">Sufficient</span>` : h`<span class="badge b-amber">Insufficient</span>`}</dd>
      <dt>Face width</dt><dd>${m.face_px} px</dd><dt>Sharpness</dt><dd>${m.sharpness}</dd><dt>Brightness</dt><dd>${m.brightness} / 255</dd><dt>Head turn</dt><dd>${m.head_turn}</dd>`);
  }
  function finish(ok, message) {
    running = false; clearInterval(timer); camera.stop(); $$('#ph').style.display = ''; $$('#cam-name').textContent = ''; hud(false, 'Camera off');
    drawFaces($$('#overlay'), camera.video, null, []);
    setMsg(ok ? 'ok' : 'error', message); paintControls(); paintSteps(ok ? 'done' : 'idle');
    if (ok) toast('Face enrollment completed successfully.');
    $$('#ph').innerHTML = ok ? `<b>Enrollment complete</b><p class="small" style="margin-top:4px">${'The encrypted template was saved. No photo was stored.'}</p>` : '<b>Camera is off</b>';
  }
  async function stopAll(message) {
    const was = running; running = false; clearInterval(timer); camera.stop();
    if (was && student) api.post(`/api/enrollment/cancel/${student.id}`).catch(() => {});
    $$('#ph').style.display = ''; hud(false, 'Camera off'); drawFaces($$('#overlay'), camera.video, null, []); setProgress(0, 0);
    if (message) setMsg('info', message); paintControls();
  }

  $$('#pick')?.addEventListener('change', (e) => { if (running) stopAll(); student = students.find((s) => String(s.id) === e.target.value) || null; setProgress(0, 0); setMsg('', ''); setHTML($$('#metrics'), ''); paintSummary(); paintConsent(); paintControls(); });
  hud(false, 'Camera off'); paintSummary(); paintConsent(); paintControls(); paintSteps();
  return () => { destroyed = true; running = false; clearInterval(timer); camera.stop(); if (enrolling && student) api.post(`/api/enrollment/cancel/${student.id}`).catch(() => {}); };
}
