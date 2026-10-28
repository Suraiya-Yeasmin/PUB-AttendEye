import { api } from '../api.js';
import { h, raw, setHTML, $, $$, fmtDateTime } from '../util.js';
import { icon } from '../icons.js';
import { toast, callout, confirmDialog, formModal, withBusy } from '../ui.js';
import { listCameras, savedCamera, saveCamera, describeCameraError } from '../camera.js';

const GROUPS = [['policy', 'Attendance decision policy (TrustScore)'], ['quality', 'Image-quality gate'], ['privacy', 'Privacy & data retention'], ['session', 'Session defaults']];

export default async function render(root, ctx) {
  const s = await api.get('/api/settings');
  const admin = s.can_edit_protected;
  const t = ctx.teacher;

  setHTML(root, h`
    <div class="page-head"><div><h1>Settings</h1><p>Profile, camera, decision policy, privacy and application information.</p></div></div>
    <div class="grid g2">
      <div class="stack">
        <section class="card"><div class="card-head"><h2>Teacher profile</h2></div><div class="card-body">
          <form id="profile" novalidate class="form-grid"><div class="field full"><label for="pn">Full name</label><input class="input" id="pn" value="${t.full_name}" maxlength="120"></div>
            <div class="field full"><label for="pe">Email</label><input class="input" id="pe" type="email" value="${t.email}"></div>
            <div class="full err" id="perr"></div><div class="full row"><button class="btn primary" type="submit">Save profile</button><button class="btn" type="button" id="pw">${icon('lock')} Change password</button>${admin ? h`<button class="btn" type="button" id="newteacher">${icon('userplus')} Add teacher account</button>` : ''}</div></form>
          <p class="hint" style="margin-top:10px">Signed in as <b>${t.username}</b> (${t.role}).</p></div></section>
        <section class="card"><div class="card-head"><h2>Camera</h2></div><div class="card-body">
          <div class="field"><label for="cams">Camera used for enrollment and attendance</label><select class="select" id="cams"><option value="">Browser default</option></select><div class="hint" id="camhint">Camera names appear after the browser has been granted camera permission once.</div></div>
          <div class="row" style="margin-top:10px"><button class="btn sm" id="camperm">${icon('camera', 'sm')} Allow camera & refresh list</button></div></div></section>
        <section class="card"><div class="card-head"><h2>Biometric data</h2></div><div class="card-body">
          <p class="small">Individual templates are removed from <a href="#/students">Students → Remove face template</a>. Students who decline use manual check-in.</p>
          ${admin ? h`<div class="row" style="margin-top:14px"><button class="btn" id="retention">${icon('clock')} Apply retention now</button><button class="btn danger" id="purge">${icon('trash')} Delete ALL face templates</button></div>` : h`<p class="hint" style="margin-top:10px">Bulk deletion and retention are restricted to administrators.</p>`}</div></section>
      </div>
      <div class="stack">
        <form id="pol" novalidate>
          ${GROUPS.map(([g, title]) => h`<section class="card" style="margin-bottom:18px"><div class="card-head"><h2>${title}</h2>${g !== 'session' && !admin ? h`<span class="badge b-slate plain">${icon('lock', 'sm')} Admin only</span>` : ''}</div><div class="card-body"><div class="form-grid">
            ${Object.entries(s.definitions).filter(([, d]) => d.group === g).map(([k, d]) => field(k, d))}</div>
            ${g === 'policy' ? callout('warn', h`<b>Limits of thresholds.</b> ${s.threshold_limitations}`) : ''}</div></section>`)}
          <div class="row"><button class="btn primary" type="submit">Save settings</button><span class="hint">Policy and quality values are protected. Only administrators can change them; every change is audit-logged.</span></div>
        </form>
        <section class="card"><div class="card-head"><h2>Application information</h2></div><div class="card-body"><dl class="kv" style="grid-template-columns:130px 1fr">
          <dt>Application</dt><dd>${s.app.name} ${s.app.version}</dd><dt>Detector</dt><dd>${s.app.models.detector}</dd><dt>Recognizer</dt><dd>${s.app.models.recognizer}</dd>
          <dt>Recognition service</dt><dd>${s.app.cv.available ? h`<span class="badge b-teal">Models loaded</span>` : h`<span class="badge b-red">Unavailable</span> <span class="small">${s.app.cv.error || ''}</span>`}</dd><dt>Database</dt><dd>${s.app.database}</dd></dl>
          <div style="margin-top:12px">${callout('info', s.app.notice)}</div></div></section>
      </div>
    </div>`);

  function field(k, d) {
    const locked = d.protected && !admin, v = s.values[k];
    if (d.type === 'boolean') return h`<div class="field full"><label class="check"><input type="checkbox" name="${k}" ${v ? raw('checked') : ''} ${locked ? raw('disabled') : ''}><span>${d.label}<br><span class="hint">${d.help}</span></span></label><div class="err" data-err="${k}"></div></div>`;
    const step = d.type === 'integer' ? '1' : '0.01';
    return h`<div class="field"><label for="s_${k}">${d.label}</label><input class="input" id="s_${k}" name="${k}" ${d.type === 'time' ? raw('type="time"') : raw(`type="number" step="${step}" min="${d.min}" max="${d.max}"`)} value="${v}" ${locked ? raw('disabled') : ''}><div class="hint">${d.help}${d.min != null ? ` (${d.min}–${d.max})` : ''}</div><div class="err" data-err="${k}"></div></div>`;
  }

  // ---- profile
  $('#profile', root).addEventListener('submit', async (e) => {
    e.preventDefault(); const err = $('#perr', root); err.textContent = '';
    try { const r = await withBusy(e.submitter || $('#profile button', root), () => api.put('/api/auth/profile', { full_name: $('#pn', root).value, email: $('#pe', root).value }), 'Saving…');
      Object.assign(ctx.teacher, r.teacher); toast('Profile saved. Reload to refresh the sidebar name.'); } catch (ex) { err.textContent = ex.message; }
  });
  $('#pw', root).addEventListener('click', () => formModal({
    title: 'Change password',
    fields: [{ name: 'current_password', label: 'Current password', type: 'password', required: true, full: true, autocomplete: 'current-password' }, { name: 'new_password', label: 'New password (min 8 characters)', type: 'password', required: true, full: true, autocomplete: 'new-password' }, { name: 'confirm', label: 'Confirm new password', type: 'password', required: true, full: true, autocomplete: 'new-password' }],
    submitText: 'Change password',
    onSubmit: async (v) => {
      if (v.new_password !== v.confirm) throw Object.assign(new Error('Passwords do not match.'), { fields: { confirm: 'Passwords do not match.' } });
      await api.post('/api/auth/password', { current_password: v.current_password, new_password: v.new_password }); toast('Password changed.');
    },
  }));
  $('#newteacher', root)?.addEventListener('click', () => formModal({
    title: 'Add teacher account',
    fields: [{ name: 'full_name', label: 'Full name', required: true }, { name: 'username', label: 'Username', required: true, pattern: /^[A-Za-z0-9._-]{3,64}$/, patternMsg: 'Letters, digits, dot, dash, underscore (3+).' }, { name: 'email', label: 'Email', type: 'email', required: true, full: true },
      { name: 'password', label: 'Temporary password (min 8)', type: 'password', required: true, autocomplete: 'new-password' }, { name: 'role', label: 'Role', type: 'select', options: [{ value: 'teacher', label: 'Teacher' }, { value: 'admin', label: 'Administrator' }] }],
    submitText: 'Create account', onSubmit: async (v) => { await api.post('/api/teachers', v); toast('Account created.'); },
  }));

  // ---- camera list
  async function fillCams() {
    const cams = await listCameras(), cur = savedCamera();
    setHTML($('#cams', root), h`<option value="">Browser default</option>${cams.filter((c) => c.deviceId).map((c, i) => h`<option value="${c.deviceId}" ${c.deviceId === cur ? raw('selected') : ''}>${c.label || `Camera ${i + 1}`}</option>`)}`);
    $('#camhint', root).textContent = cams.length ? `${cams.length} camera(s) found.` : 'No camera found, or permission has not been granted yet.';
  }
  $('#cams', root).addEventListener('change', (e) => { saveCamera(e.target.value); toast('Camera preference saved on this browser.'); });
  $('#camperm', root).addEventListener('click', async () => {
    try { const st = await navigator.mediaDevices.getUserMedia({ video: true }); st.getTracks().forEach((x) => x.stop()); await fillCams(); toast('Camera permission granted.'); }
    catch (e) { toast(describeCameraError(e), 'error', 7000); }
  });
  fillCams();

  // ---- policy
  $('#pol', root).addEventListener('submit', async (e) => {
    e.preventDefault(); $$('[data-err]', root).forEach((x) => (x.textContent = ''));
    const values = {};
    for (const [k, d] of Object.entries(s.definitions)) {
      if (d.protected && !admin) continue;
      const el = e.target.elements[k]; if (!el) continue;
      values[k] = d.type === 'boolean' ? el.checked : d.type === 'time' ? el.value : Number(el.value);
      if (d.type !== 'boolean' && d.type !== 'time' && el.value === '') { $(`[data-err="${k}"]`, root).textContent = 'A value is required.'; return; }
    }
    try { const r = await withBusy($('#pol button[type=submit]', root), () => api.put('/api/settings', { values }), 'Saving…'); Object.assign(s.values, r.values); toast('Settings saved.'); }
    catch (ex) { Object.entries(ex.fields || {}).forEach(([k, m]) => { const el = $(`[data-err="${k}"]`, root); if (el) el.textContent = m; }); toast(ex.message, 'error'); }
  });

  // ---- admin data actions
  $('#retention', root)?.addEventListener('click', async () => {
    if (!(await confirmDialog({ title: 'Apply retention now?', message: `Recognition events and evaluation samples older than ${s.values.event_retention_days} days will be permanently deleted. Pending reviews are kept.`, confirmText: 'Delete old data', danger: true }))) return;
    try { const r = await api.post('/api/settings/apply-retention'); toast(`Deleted ${r.recognition_events_deleted} event(s) and ${r.evaluation_samples_deleted} sample(s).`); } catch (e) { toast(e.message, 'error'); }
  });
  $('#purge', root)?.addEventListener('click', () => formModal({
    title: 'Delete ALL face templates', intro: callout('error', 'Every student loses camera attendance and must consent and enroll again. This cannot be undone. Attendance records are kept.'),
    fields: [{ name: 'confirm', label: 'Type DELETE ALL TEMPLATES to confirm', required: true, full: true }], submitText: 'Delete everything',
    onSubmit: async (v) => { const r = await api.post('/api/settings/purge-biometrics', { confirm: v.confirm }); toast(`${r.deleted} template(s) deleted.`); },
  }));
}
