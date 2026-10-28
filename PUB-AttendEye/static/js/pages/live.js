import { api, ApiError } from '../api.js';
import { h, raw, setHTML, $, fmtDate, fmtTimeSec, fmtDateTime } from '../util.js';
import { icon } from '../icons.js';
import { toast, callout, confirmDialog, decisionBadge, sessionBadge, empty, withBusy } from '../ui.js';
import { Camera, describeCameraError, drawFaces } from '../camera.js';

const STATE = {
  verified: { color: '#0d8a77', status: 'Attendance recorded', tone: 'teal' },
  pending: { color: '#5b5fe0', status: 'Recognition pending', tone: 'indigo' },
  review: { color: '#d98a06', status: 'Uncertain match - needs teacher review', tone: 'amber' },
  unknown: { color: '#dc2626', status: 'Unknown identity', tone: 'red' },
  poor_quality: { color: '#64748b', status: 'Poor image quality', tone: 'slate' },
  duplicate: { color: '#2563eb', status: 'Duplicate - already present', tone: 'blue' },
};
const INTERVAL_MS = 700;

export default async function render(root, ctx) {
  let sessions = [], session = null, scanning = false, cam = null, last = null, lastAt = 0, rafId = 0, tickTimer = 0, evTimer = 0, destroyed = false;
  let camState = 'off', banner = null, noFace = false, primary = null, svcStatus = null;

  // ---------- load sessions ----------
  async function loadSessions() {
    const [a, b] = await Promise.all([api.get('/api/sessions?status=active'), api.get('/api/sessions?status=scheduled&limit=60')]);
    sessions = [...a.items, ...b.items];
    const want = ctx.params.get('session');
    if (want && !sessions.find((s) => String(s.id) === want)) { try { const d = await api.get(`/api/sessions/${want}`); sessions.unshift(d); } catch {} }
    session = sessions.find((s) => String(s.id) === (want || String(session?.id))) || sessions.find((s) => s.status === 'active') || sessions[0] || null;
  }
  try { svcStatus = await api.get('/api/recognition/status'); } catch (e) { svcStatus = { available: false, error: e.message }; }
  await loadSessions();

  function shell() {
    setHTML(root, h`
      <div class="page-head"><div><h1>Live Attendance</h1><p>Webcam recognition proposes a candidate; attendance is only recorded when the policy accepts it or you confirm it.</p></div>
        <div class="row"><label class="label" for="sess">Session</label>
        <select class="select" id="sess" style="min-width:300px" ${scanning ? raw('disabled') : ''}>${sessions.length ? sessions.map((s) => h`<option value="${s.id}" ${session?.id === s.id ? 'selected' : ''}>${s.course_code} · Sec ${s.section} · ${fmtDate(s.session_date)} ${s.start_time} (${s.status})</option>`) : h`<option value="">No active or scheduled sessions</option>`}</select></div></div>
      <div class="grid g-live">
        <div class="stack">
          <section class="card"><div class="card-body" style="padding:14px">
            <div class="cam" id="cam"><video id="video" playsinline muted></video><canvas id="overlay"></canvas>
              <div class="hud" id="hud"></div>
              <div class="placeholder" id="ph">${icon('camera')}<b>Camera is off</b><p class="small" style="margin-top:4px">Press Start Camera. Your browser will ask permission to use the webcam.</p></div></div>
            <div class="row" style="margin-top:14px" id="controls"></div>
            <div id="banner" style="margin-top:12px"></div>
            <div class="legend" style="margin-top:14px"><span><i style="background:${STATE.verified.color}"></i>Verified</span><span><i style="background:${STATE.pending.color}"></i>Pending</span><span><i style="background:${STATE.review.color}"></i>Uncertain</span><span><i style="background:${STATE.unknown.color}"></i>Unknown</span><span><i style="background:${STATE.poor_quality.color}"></i>Poor quality</span><span><i style="background:${STATE.duplicate.color}"></i>Duplicate</span></div>
          </div></section>
          <section class="card"><div class="card-head"><h2>AttendEye TrustScore</h2><span class="small muted">Certainty of this recognition attempt, not of a person</span></div><div class="card-body" id="trust"></div></section>
        </div>
        <div class="stack">
          <section class="card"><div class="card-body"><div class="row spread"><div><div class="label">Verified attendance records</div><div style="font-size:34px;font-weight:700;letter-spacing:-.02em" id="verified">—</div></div><div class="right" id="sess-info"></div></div>
            <p class="hint" style="margin-top:8px">Frames are analysed about every ${INTERVAL_MS / 1000} s while scanning. The activity list refreshes after every new event and every 3 s (polling, not push).</p><div id="svc" style="margin-top:10px"></div></div></section>
          <section class="card"><div class="card-head"><h2>Recognition activity</h2></div><div class="card-body" style="max-height:340px;overflow:auto" id="events">${empty({ icon: 'clock', title: 'No events yet', text: 'Events appear here as faces are processed.' })}</div></section>
          <section class="card"><div class="card-head"><h2>Manual check-in</h2><span class="badge plain b-slate">Alternative to face recognition</span></div><div class="card-body"><p class="hint" style="margin-bottom:8px">For students who did not consent to biometrics, or when recognition is unavailable, mark attendance directly. Recorded as “Manual (teacher)”.</p><div id="manual" style="max-height:260px;overflow:auto"></div></div></section>
        </div>
      </div>`);
    cam = new Camera($('#video', root));
    cam.onEnded = () => { camState = 'off'; stopScanning('The camera was disconnected.'); paintCam(); };
    $('#sess', root)?.addEventListener('change', async (e) => { session = sessions.find((s) => String(s.id) === e.target.value) || null; last = null; primary = null; paintAll(); refreshEvents(); });
    paintAll(); refreshEvents();
  }

  // ---------- painting ----------
  function paintAll() { paintControls(); paintCam(); paintTrust(); paintSvc(); paintSessionInfo(); }
  function paintSvc() {
    const el = $('#svc', root); if (!el) return;
    if (!svcStatus?.available) setHTML(el, callout('error', h`<b>Recognition service unavailable.</b> ${svcStatus?.error || ''} No identity will be shown or recorded. Use manual check-in meanwhile.`));
    else if (!svcStatus.enrolled_templates) setHTML(el, callout('warn', h`No face templates are enrolled yet, so every face will be treated as unknown. <a href="#/enroll">Enroll students</a> or use manual check-in.`));
    else setHTML(el, h`<span class="badge b-teal">Recognition ready · ${svcStatus.enrolled_templates} template${svcStatus.enrolled_templates === 1 ? '' : 's'}</span>`);
  }
  function paintSessionInfo() {
    const el = $('#sess-info', root); if (!el) return;
    setHTML(el, session ? h`${sessionBadge(session.status)}<div class="small muted" style="margin-top:4px">${session.course_code} · ${session.course_name}</div>` : h`<span class="small muted">No session selected</span>`);
  }
  function paintControls() {
    const el = $('#controls', root); if (!el) return;
    const on = cam?.running;
    setHTML(el, h`<button class="btn" id="b-cam" ${on || camState === 'starting' ? raw('disabled') : ''}>${icon('camera')} Start Camera</button>
      <button class="btn" id="b-cam-stop" ${!on ? raw('disabled') : ''}>${icon('stop')} Stop Camera</button>
      <button class="btn primary" id="b-start" ${scanning || !session ? raw('disabled') : ''}>${icon('play')} Start Attendance</button>
      <button class="btn danger" id="b-end" ${session?.status !== 'active' ? raw('disabled') : ''}>${icon('stop')} End Attendance</button>`);
    $('#b-cam', root).onclick = startCamera; $('#b-cam-stop', root).onclick = () => { stopScanning(); cam.stop(); camState = 'off'; paintAll(); };
    $('#b-start', root).onclick = startAttendance; $('#b-end', root).onclick = endAttendance;
    const sel = $('#sess', root); if (sel) sel.disabled = scanning;
  }
  function paintCam() {
    const hud = $('#hud', root), ph = $('#ph', root); if (!hud) return;
    const on = cam?.running;
    ph.style.display = on ? 'none' : 'block';
    if (!on) { setHTML(ph, h`${icon('camera')}<b>${camState === 'error' ? 'Camera unavailable' : camState === 'starting' ? 'Starting camera…' : 'Camera is off'}</b><p class="small" style="margin-top:4px">${camState === 'error' ? '' : 'Press Start Camera. Your browser will ask permission to use the webcam.'}</p>`); drawFaces($('#overlay', root), null, null, null); }
    setHTML(hud, h`<span class="chip ${on ? 'on' : camState === 'error' ? 'bad' : ''}"><i></i>${on ? 'Camera connected' : camState === 'error' ? 'Camera error' : 'Camera off'}</span>${scanning ? h`<span class="chip scan"><i></i>Scanning</span>` : ''}${scanning && noFace ? h`<span class="chip"><i></i>No face detected</span>` : ''}`);
  }
  function paintTrust() {
    const el = $('#trust', root); if (!el) return;
    if (!primary) { setHTML(el, h`<p class="muted">${scanning ? 'Waiting for a face…' : 'No recognition attempt yet. Start attendance to see decision details here.'}</p>`); return; }
    const t = primary.trust, st = STATE[primary.state] || STATE.poor_quality, q = t.quality_metrics;
    setHTML(el, h`<div class="trust"><div class="head tone-${st.tone}">${icon(primary.state === 'verified' ? 'checkcircle' : primary.state === 'review' ? 'inbox' : 'alert')}<span>${t.decision_label}</span><span style="margin-left:auto;font-weight:600;font-size:12.5px">${primary.state === 'verified' ? 'Final decision' : primary.state === 'poor_quality' ? 'No decision made' : 'Candidate only - not final'}</span></div>
      <dl><dt>Candidate</dt><dd>${primary.candidate ? `${primary.candidate.full_name} (${primary.candidate.student_id})` : 'None'}</dd>
      <dt><span class="tip" title="${svcStatus?.similarity_explainer || 'Cosine similarity between face embeddings; not a probability.'}">Similarity score ⓘ</span></dt><dd>${t.similarity == null ? '—' : t.similarity.toFixed(2)} <span class="small muted">(cosine, −1…1)</span></dd>
      <dt>Gap to next-best student</dt><dd>${t.runner_up_gap == null ? '—' : t.runner_up_gap.toFixed(2)}</dd>
      <dt>Face detection</dt><dd>Detected · score ${q.detector_score}</dd>
      <dt>Image quality</dt><dd>${t.quality_ok ? 'Passed' : 'Failed: ' + t.quality_messages.join(' ')}</dd>
      <dt>Duplicate attendance</dt><dd>${t.duplicate ? 'Yes - already present' : 'No'}</dd>
      <dt>Teacher review required</dt><dd>${t.review_required ? 'Yes' : 'No'}</dd></dl>
      <div style="padding:0 14px 14px"><div class="label">Reason</div><p>${t.reason || '—'}</p></div></div>
      <p class="hint" style="margin-top:8px">Policy: accept ≥ ${svcStatus?.policy?.accept_threshold}, review ≥ ${svcStatus?.policy?.review_threshold}, margin ≥ ${svcStatus?.policy?.margin}, ${svcStatus?.policy?.confirm_frames} agreeing frames. Defaults are not calibrated to your room - check System Evaluation.</p>`);
  }
  const showBanner = (kind, text) => { banner = text ? { kind, text } : null; const el = $('#banner', root); if (el) setHTML(el, banner ? callout(kind, banner.text) : ''); };

  // ---------- camera & scanning ----------
  async function startCamera() {
    camState = 'starting'; showBanner('', ''); paintAll();
    try { await cam.start(); camState = 'on'; }
    catch (e) { camState = 'error'; showBanner('error', describeCameraError(e)); }
    paintAll();
    if (cam.running) loopDraw();
  }
  async function startAttendance() {
    if (!session) return toast('Choose a session first.', 'warn');
    if (!svcStatus?.available) { try { svcStatus = await api.get('/api/recognition/status'); } catch {} paintSvc(); if (!svcStatus?.available) return showBanner('error', 'Recognition service is unavailable, so camera attendance cannot start. Use manual check-in.'); }
    if (session.status === 'scheduled') {
      if (!(await confirmDialog({ title: 'Start this session?', message: `This will start ${session.course_code} (section ${session.section}) and begin recording attendance.`, confirmText: 'Start session & scan' }))) return;
      try { const s = await api.post(`/api/sessions/${session.id}/start`); Object.assign(session, s); } catch (e) { return showBanner('error', e.message); }
    } else if (session.status !== 'active') return showBanner('error', 'This session is not active.');
    if (!cam.running) { await startCamera(); if (!cam.running) return; }
    showBanner('', ''); scanning = true; noFace = false; paintAll(); paintSessionInfo(); tick(); refreshEvents();
    if (window.__refreshPending) window.__refreshPending();
  }
  function stopScanning(msg) {
    scanning = false; clearTimeout(tickTimer); if (msg) showBanner('warn', msg); if (!destroyed) paintAll();
  }
  async function endAttendance() {
    const ok = await confirmDialog({ title: 'End attendance and close the session?', message: 'Scanning stops and the session is marked Completed. No further attendance can be recorded unless you reopen it. Pending review cases stay in the Review Queue.', confirmText: 'End attendance', danger: true });
    if (!ok) return;
    stopScanning();
    try { const s = await api.post(`/api/sessions/${session.id}/close`); sessions = sessions.filter((x) => x.id !== session.id); toast(`Session closed with ${last?.verified_total ?? 0} verified records.`); session = sessions[0] || null; last = null; primary = null; shell(); }
    catch (e) { showBanner('error', e.message); }
  }
  async function tick() {
    if (!scanning || destroyed) return;
    const t0 = performance.now();
    try {
      const blob = await cam.capture(640);
      if (blob) { const r = await api.frame(`/api/recognition/frame?session_id=${session.id}`, blob); onResult(r); }
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) { /* undecodable frame: skip */ }
      else if (e instanceof ApiError && e.status === 503) { svcStatus = { ...(svcStatus || {}), available: false, error: e.message }; paintSvc(); return stopScanning('Recognition service unavailable - scanning paused. Nothing was recorded. ' + e.message); }
      else if (e instanceof ApiError && e.status === 409) { session.status = 'completed'; paintSessionInfo(); return stopScanning(e.message); }
      else if (e instanceof ApiError && e.status === 0) return stopScanning(e.message);
      else if (e instanceof ApiError && e.status === 401) return;
      else return stopScanning('Scanning paused: ' + (e.message || 'unexpected error'));
    }
    if (scanning && !destroyed) tickTimer = setTimeout(tick, Math.max(0, INTERVAL_MS - (performance.now() - t0)));
  }
  function onResult(r) {
    noFace = r.face_count === 0;
    last = r; lastAt = performance.now();
    last.draw = r.faces.map((f) => {
      const st = STATE[f.state] || STATE.poor_quality;
      const lines = [];
      if (f.candidate) lines.push((f.state === 'verified' ? '' : 'Candidate: ') + `${f.candidate.full_name} · ${f.candidate.student_id}`);
      lines.push(st.status);
      return { bbox: f.bbox, color: st.color, lines };
    });
    primary = r.faces[0] || null; // largest face first (server sorts by area)
    const v = $('#verified', root); if (v) v.textContent = r.verified_total;
    paintCamHud(); paintTrust();
    const created = r.faces.filter((f) => f.attendance_created);
    created.forEach((f) => toast(`Attendance recorded: ${f.candidate.full_name} (${f.candidate.student_id})`));
    if (created.length || r.faces.some((f) => ['review', 'duplicate', 'unknown'].includes(f.state))) { refreshEvents(); if (created.length) refreshManual(); if (window.__refreshPending) window.__refreshPending(); }
  }
  function paintCamHud() { paintCam(); }
  function loopDraw() {
    cancelAnimationFrame(rafId);
    const step = () => {
      if (destroyed) return;
      const c = $('#overlay', root);
      if (c) { const fresh = last && performance.now() - lastAt < 1600; drawFaces(c, $('#video', root), fresh ? last.frame : null, fresh ? last.draw : null); }
      rafId = requestAnimationFrame(step);
    };
    step();
  }

  // ---------- activity & manual ----------
  async function refreshEvents() {
    clearTimeout(evTimer);
    if (destroyed) return;
    const el = $('#events', root);
    if (session && el) {
      try {
        const r = await api.get(`/api/recognition/events?session_id=${session.id}&limit=30`);
        const v = $('#verified', root); if (v) v.textContent = r.verified_total;
        setHTML(el, r.items.length ? r.items.map(eventRow) : empty({ icon: 'clock', title: 'No events yet', text: 'Events appear here as faces are processed.' }));
      } catch {}
      refreshManual();
    } else if (el) { setHTML(el, empty({ icon: 'calendar', title: 'No session selected', text: 'Create a session under Classes & Sessions.', action: h`<a class="btn primary" href="#/classes">Go to sessions</a>` })); }
    evTimer = setTimeout(refreshEvents, scanning ? 3000 : 8000);
  }
  function eventRow(e) {
    const tone = { accepted: 'tone-teal', needs_review: 'tone-amber', unknown: 'tone-red', duplicate: 'tone-blue' }[e.decision] || 'tone-slate';
    const ic = { accepted: 'checkcircle', needs_review: 'inbox', unknown: 'userx', duplicate: 'shield' }[e.decision] || 'info';
    const who = e.student_name ? (e.decision === 'needs_review' ? 'Candidate: ' : '') + `${e.student_name} (${e.student_id})` : 'Unidentified face';
    return h`<div class="event"><span class="dot ${tone}">${icon(ic)}</span><div style="min-width:0;flex:1"><div class="row spread" style="gap:6px"><b>${who}</b><span class="small muted nowrap">${fmtTimeSec(e.timestamp)}</span></div><div>${decisionBadge(e.decision, e.decision_label)} ${e.review_status === 'pending' ? h`<span class="badge b-amber">Review pending</span>` : e.review_status !== 'none' ? h`<span class="badge b-slate">Review: ${e.review_status}</span>` : ''}</div><div class="reason">${e.reason}</div></div></div>`;
  }
  async function refreshManual() {
    const el = $('#manual', root); if (!el || !session) return;
    try {
      const d = await api.get(`/api/sessions/${session.id}`);
      if (!d.roster_size) { setHTML(el, callout('info', h`This class has no roster. <a href="#/classes">Assign students</a> to enable manual check-in lists.`)); return; }
      if (!d.absent.length) { setHTML(el, h`<p class="muted">Everyone on the roster has an attendance record.</p>`); return; }
      setHTML(el, d.absent.map((s) => h`<div class="list-item" style="align-items:center"><div style="flex:1;min-width:0"><b>${s.full_name}</b><div class="small muted">${s.student_id} ${s.biometric_consent === 'declined' ? h`· <span class="badge plain b-slate">Declined biometrics</span>` : ''}</div></div><button class="btn sm" data-mark="${s.id}" ${d.status !== 'active' ? raw('disabled') : ''}>Mark present</button></div>`));
      el.querySelectorAll('[data-mark]').forEach((b) => b.addEventListener('click', async () => {
        try { await withBusy(b, () => api.post('/api/attendance/manual', { session_id: session.id, student_pk: Number(b.dataset.mark) })); toast('Marked present (manual).'); refreshEvents(); }
        catch (e) { toast(e.message, 'error'); refreshManual(); }
      }));
    } catch {}
  }

  shell();
  return () => { destroyed = true; scanning = false; clearTimeout(tickTimer); clearTimeout(evTimer); cancelAnimationFrame(rafId); cam?.stop(); };
}
