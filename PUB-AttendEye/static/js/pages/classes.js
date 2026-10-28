import { api, download } from '../api.js';
import { h, raw, setHTML, $, $$, qs, today, addMinutes, fmtDate, fmtDateTime, fmtTime } from '../util.js';
import { icon } from '../icons.js';
import { toast, empty, callout, confirmDialog, formModal, openModal, menu, sessionBadge, attBadge, methodLabel, withBusy } from '../ui.js';

const CLASS_FIELDS = [
  { name: 'code', label: 'Course code', required: true, maxlength: 32, pattern: /^[A-Za-z0-9 ._/-]{2,32}$/, patternMsg: 'Use letters, digits, space, dot, dash or slash.' },
  { name: 'section', label: 'Section', required: true, maxlength: 32 },
  { name: 'name', label: 'Course name', required: true, maxlength: 160, full: true },
  { name: 'department', label: 'Department (optional)', maxlength: 80, full: true },
];

export default async function render(root, ctx) {
  const isAdmin = ctx.teacher.role === 'admin';
  let tab = ctx.params.get('tab') === 'sessions' ? 'sessions' : 'classes';
  let classes = [], sessions = [], teachers = [], defaults = { default_session_start: '09:00', default_session_minutes: 90 };
  const sf = { class_id: ctx.params.get('class') || '', status: '', date_from: '', date_to: '' };

  try { const s = await api.get('/api/settings'); defaults = s.values; } catch {}
  if (isAdmin) { try { teachers = (await api.get('/api/teachers')).items; } catch {} }

  setHTML(root, h`
    <div class="page-head"><div><h1>Classes & sessions</h1><p>Create classes, assign rosters and run attendance sessions.</p></div>
      <div class="row"><button class="btn" id="new-session">${icon('calendar')} New session</button><button class="btn primary" id="new-class">${icon('plus')} New class</button></div></div>
    <div class="tabs" role="tablist" style="margin-bottom:16px"><button class="tab" role="tab" data-tab="classes">Classes</button><button class="tab" role="tab" data-tab="sessions">Sessions & history</button></div>
    <section class="card"><div id="body"></div></section>`);

  async function loadClasses() { classes = (await api.get('/api/classes')).items; }
  async function loadSessions() { sessions = (await api.get('/api/sessions' + qs(sf))).items; }
  async function paint() {
    $$('.tab', root).forEach((t) => t.classList.toggle('active', t.dataset.tab === tab));
    const body = $('#body', root);
    try { await loadClasses(); if (tab === 'sessions') await loadSessions(); } catch (e) { setHTML(body, callout('error', e.message)); return; }
    setHTML(body, tab === 'classes' ? classesView() : sessionsView());
  }

  // ---------------- classes ----------------
  function classesView() {
    if (!classes.length) return empty({ icon: 'book', title: 'No classes yet', text: 'Create a class, add its roster, then schedule sessions.', action: h`<button class="btn primary" data-act="new-class">${icon('plus')} Create class</button>` });
    return h`<div class="table-wrap"><table class="t"><thead><tr><th>Course</th><th>Section</th><th>Teacher</th><th>Roster</th><th class="right"><span class="sr-only">Actions</span></th></tr></thead><tbody>
      ${classes.map((c) => h`<tr><td><b>${c.code}</b><div class="sub">${c.name}</div></td><td>${c.section}</td><td>${c.teacher_name}</td>
        <td>${c.roster_size ? `${c.roster_size} students` : h`<span class="badge b-amber">No roster</span>`}</td>
        <td class="right"><div class="row" style="justify-content:flex-end"><button class="btn sm" data-act="new-session" data-id="${c.id}">${icon('plus', 'sm')} Session</button>${menu([
          { action: 'edit-class', id: c.id, label: 'Edit class', icon: 'edit' }, { action: 'roster', id: c.id, label: 'Manage roster', icon: 'users' },
          { action: 'history', id: c.id, label: 'Session history', icon: 'history' }])}</div></td></tr>`)}</tbody></table></div>`;
  }
  function classForm(c) {
    const fields = [...CLASS_FIELDS];
    if (isAdmin && teachers.length) fields.push({ name: 'teacher_id', label: 'Teacher', type: 'select', full: true, options: teachers.map((t) => ({ value: t.id, label: `${t.full_name} (${t.username})` })), default: ctx.teacher.id });
    formModal({
      title: c ? 'Edit class' : 'Create class', fields, values: c || {}, submitText: c ? 'Save changes' : 'Create class',
      onSubmit: async (v) => {
        const body = { code: v.code, name: v.name, section: v.section, department: v.department || null };
        if (v.teacher_id) body.teacher_id = Number(v.teacher_id);
        if (c) await api.put(`/api/classes/${c.id}`, body); else await api.post('/api/classes', body);
        toast(c ? 'Class updated.' : 'Class created. Now add its roster.'); paint();
      },
    });
  }
  async function rosterModal(c) {
    let detail, all;
    try { [detail, all] = await Promise.all([api.get(`/api/classes/${c.id}`), api.get('/api/students?page_size=200&status=active')]); } catch (e) { toast(e.message, 'error'); return; }
    const inRoster = new Set(detail.roster.map((s) => s.id));
    const m = openModal({
      title: `Roster - ${c.code} (Sec ${c.section})`, wide: true,
      body: h`<div class="row" style="margin-bottom:12px"><div class="input-wrap grow" style="flex:1">${icon('search')}<input class="input" id="rq" placeholder="Filter students" aria-label="Filter students"></div>
        <button class="btn sm" id="add-section">${icon('plus', 'sm')} Add all in section ${c.section}</button></div>
        <div id="rlist" style="max-height:380px;overflow:auto;border:1px solid var(--border);border-radius:10px">${all.items.length ? all.items.map((s) => h`<label class="check" style="padding:9px 12px;border-bottom:1px solid var(--border)" data-name="${(s.full_name + ' ' + s.student_id).toLowerCase()}"><input type="checkbox" value="${s.id}" ${inRoster.has(s.id) ? raw('checked') : ''}><span><b>${s.full_name}</b> <span class="muted small">${s.student_id} · ${s.department} · Sec ${s.section}</span></span></label>`) : empty({ title: 'No active students', icon: 'users' })}</div>
        <p class="hint" style="margin-top:8px"><span id="rcount"></span> Absence is calculated against this roster, so keep it accurate.</p>`,
      footer: h`<button class="btn" data-close>Cancel</button><button class="btn primary" data-save>Save roster</button>`,
      onMount: (m) => {
        const count = () => { m.$('#rcount').textContent = `${m.$$('#rlist input:checked').length} selected.`; }; count();
        m.$('#rlist').addEventListener('change', count);
        m.$('#rq').addEventListener('input', (e) => { const q = e.target.value.toLowerCase(); m.$$('#rlist label').forEach((l) => { l.style.display = l.dataset.name.includes(q) ? '' : 'none'; }); });
        m.$('#add-section').addEventListener('click', async (e) => {
          try { const r = await withBusy(e.currentTarget, () => api.post(`/api/classes/${c.id}/roster/by-section`, { section: c.section }), 'Adding…');
            toast(r.added ? `${r.added} student(s) added to the roster.` : 'No new active students in that section.'); m.close(); paint(); } catch (ex) { toast(ex.message, 'error'); }
        });
        m.$('[data-save]').addEventListener('click', async (e) => {
          const ids = m.$$('#rlist input:checked').map((i) => Number(i.value));
          try { await withBusy(e.currentTarget, () => api.put(`/api/classes/${c.id}/roster`, { student_pks: ids }), 'Saving…'); toast(`Roster saved (${ids.length} students).`); m.close(); paint(); } catch (ex) { toast(ex.message, 'error'); }
        });
      },
    });
    return m;
  }

  // ---------------- sessions ----------------
  function sessionsView() {
    const filters = h`<div class="toolbar">
      <select class="select" id="sf-class" aria-label="Class"><option value="">All classes</option>${classes.map((c) => h`<option value="${c.id}" ${String(c.id) === String(sf.class_id) ? 'selected' : ''}>${c.code} · Sec ${c.section}</option>`)}</select>
      <select class="select" id="sf-status" aria-label="Status"><option value="">All statuses</option>${['scheduled', 'active', 'completed', 'cancelled'].map((s) => h`<option value="${s}" ${sf.status === s ? 'selected' : ''}>${s[0].toUpperCase() + s.slice(1)}</option>`)}</select>
      <label class="small muted" for="sf-from">From</label><input class="input" style="width:auto" type="date" id="sf-from" value="${sf.date_from}">
      <label class="small muted" for="sf-to">To</label><input class="input" style="width:auto" type="date" id="sf-to" value="${sf.date_to}"></div>`;
    if (!sessions.length) return h`${filters}${empty({ icon: 'calendar', title: 'No sessions found', text: classes.length ? 'Create a session to start taking attendance.' : 'Create a class first.', action: classes.length ? h`<button class="btn primary" data-act="new-session">${icon('plus')} New session</button>` : '' })}`;
    return h`${filters}<div class="table-wrap"><table class="t"><thead><tr><th>Date</th><th>Course</th><th>Section</th><th>Teacher</th><th>Time</th><th>Status</th><th>Present</th><th class="right"><span class="sr-only">Actions</span></th></tr></thead><tbody>
      ${sessions.map((s) => h`<tr><td class="nowrap">${fmtDate(s.session_date)}</td><td><b>${s.course_code}</b><div class="sub">${s.course_name}</div></td><td>${s.section}</td><td>${s.teacher_name}</td><td class="nowrap">${s.start_time}–${s.end_time}</td><td>${sessionBadge(s.status)}</td>
        <td>${s.present_count ?? 0}${s.roster_size ? ` / ${s.roster_size}` : ''}</td>
        <td class="right"><div class="row" style="justify-content:flex-end">
          ${s.status === 'scheduled' ? h`<button class="btn sm primary" data-act="start" data-id="${s.id}">${icon('play', 'sm')} Start</button>` : ''}
          ${s.status === 'active' ? h`<a class="btn sm" href="#/live?session=${s.id}">${icon('camera', 'sm')} Live</a><button class="btn sm danger" data-act="close" data-id="${s.id}">${icon('stop', 'sm')} Close</button>` : ''}
          ${menu([{ action: 'detail', id: s.id, label: 'View details', icon: 'file' },
            ...(s.status === 'completed' ? [{ action: 'reopen', id: s.id, label: 'Reopen session', icon: 'refresh' }] : []),
            ...(s.status === 'scheduled' ? [{ action: 'cancel', id: s.id, label: 'Cancel session', icon: 'x', danger: true }] : []),
            { action: 'export', id: s.id, label: 'Export CSV', icon: 'download' }])}</div></td></tr>`)}</tbody></table></div>
      <div class="t-foot"><span>${sessions.length} session(s)</span></div>`;
  }
  function sessionForm(classId) {
    if (!classes.length) { toast('Create a class first.', 'warn'); return; }
    const start = defaults.default_session_start || '09:00';
    formModal({
      title: 'Create session',
      fields: [
        { name: 'class_id', label: 'Class', type: 'select', full: true, options: classes.map((c) => ({ value: c.id, label: `${c.code} · Sec ${c.section} - ${c.name}` })), default: classId || classes[0].id },
        { name: 'session_date', label: 'Date', type: 'date', required: true, default: today() },
        { name: 'start_time', label: 'Start time', type: 'time', required: true, default: start },
        { name: 'end_time', label: 'End time', type: 'time', required: true, default: addMinutes(start, defaults.default_session_minutes || 90) },
      ],
      submitText: 'Create session',
      onSubmit: async (v) => {
        const s = await api.post('/api/sessions', { class_id: Number(v.class_id), session_date: v.session_date, start_time: v.start_time, end_time: v.end_time });
        toast('Session scheduled. Start it when the class begins.'); tab = 'sessions'; sf.class_id = String(s.class_id); paint();
      },
    });
  }
  async function detail(id) {
    let d; try { d = await api.get(`/api/sessions/${id}`); } catch (e) { toast(e.message, 'error'); return; }
    openModal({
      title: `${d.course_code} · ${fmtDate(d.session_date)}`, wide: true,
      body: h`<div class="row" style="gap:12px;margin-bottom:14px">${sessionBadge(d.status)}<span class="muted small">Section ${d.section} · ${d.start_time}–${d.end_time} · ${d.teacher_name}</span></div>
        <div class="grid g3" style="gap:10px;margin-bottom:16px">
          <div class="stat"><div class="top"><span>Present</span></div><div class="num">${d.present_count}</div><div class="sub">of ${d.roster_size || '—'} on roster</div></div>
          <div class="stat"><div class="top"><span>Absent</span></div><div class="num">${d.roster_size ? d.absent.length : '—'}</div><div class="sub">${d.roster_size ? 'on roster, no record' : 'no roster assigned'}</div></div>
          <div class="stat"><div class="top"><span>Recognition</span></div><div class="num">${d.recognition.pending_reviews}</div><div class="sub">pending reviews · ${d.recognition.unknown} unknown · ${d.recognition.duplicate} duplicates</div></div></div>
        <h3 style="margin-bottom:8px">Attendance records</h3>
        ${d.attendance.length ? h`<div class="table-wrap" style="max-height:240px;overflow:auto"><table class="t"><thead><tr><th>Student</th><th>Time</th><th>Method</th><th>Status</th></tr></thead><tbody>${d.attendance.map((a) => h`<tr><td><b>${a.student_name}</b><div class="sub">${a.student_id}</div></td><td>${fmtTime(a.timestamp)}</td><td>${methodLabel(a.method)}</td><td>${attBadge(a.status)}</td></tr>`)}</tbody></table></div>` : h`<p class="muted">No attendance recorded yet.</p>`}
        ${d.absent.length ? h`<h3 style="margin:16px 0 8px">Absent (${d.absent.length})</h3><p class="small">${d.absent.map((s) => `${s.full_name} (${s.student_id})`).join(', ')}</p>` : ''}`,
      footer: h`<button class="btn" data-close>Close</button><button class="btn" data-export>${icon('download')} Export CSV</button><a class="btn" href="#/history?session=${d.id}" data-close>Open in history</a>`,
      onMount: (m) => m.$('[data-export]').addEventListener('click', () => exportCsv(d.id)),
    });
  }
  async function exportCsv(id) { try { const r = await download(`/api/reports/export?kind=session&session_id=${id}`, 'attendance.csv'); toast(`Exported ${r.rows} row(s) to ${r.name}.`); } catch (e) { toast(e.message, 'error'); } }

  async function act(action, id) {
    const sess = sessions.find((s) => String(s.id) === String(id)); const cls = classes.find((c) => String(c.id) === String(id));
    try {
      switch (action) {
        case 'new-class': return classForm();
        case 'edit-class': return classForm(cls);
        case 'roster': return rosterModal(cls);
        case 'history': tab = 'sessions'; sf.class_id = String(id); return paint();
        case 'new-session': return sessionForm(id ? Number(id) : undefined);
        case 'detail': return detail(id);
        case 'export': return exportCsv(id);
        case 'start':
          if (!(await confirmDialog({ title: 'Start this session?', message: `Attendance will be recorded for ${sess.course_code} (Section ${sess.section}) until you close the session.`, confirmText: 'Start session' }))) return;
          await api.post(`/api/sessions/${id}/start`); toast('Session started.'); return paint();
        case 'close':
          if (!(await confirmDialog({ title: 'Close this session?', message: 'No further attendance can be recorded unless you reopen it. Pending review cases can only be confirmed while the session is active.', confirmText: 'Close session', danger: true }))) return;
          await api.post(`/api/sessions/${id}/close`); toast('Session closed.'); return paint();
        case 'reopen':
          if (!(await confirmDialog({ title: 'Reopen this session?', message: 'The session becomes active again and accepts attendance.', confirmText: 'Reopen' }))) return;
          await api.post(`/api/sessions/${id}/reopen`); toast('Session reopened.'); return paint();
        case 'cancel':
          if (!(await confirmDialog({ title: 'Cancel this session?', message: 'A cancelled session never accepts attendance and is excluded from reports.', confirmText: 'Cancel session', danger: true }))) return;
          await api.post(`/api/sessions/${id}/cancel`); toast('Session cancelled.'); return paint();
      }
    } catch (e) { toast(e.message, 'error'); }
  }

  root.addEventListener('click', (e) => {
    const t = e.target.closest('.tab'); if (t) { tab = t.dataset.tab; paint(); return; }
    const b = e.target.closest('[data-action],[data-act]'); if (b) act(b.dataset.action || b.dataset.act, b.dataset.id);
  });
  root.addEventListener('change', (e) => {
    const m = { 'sf-class': 'class_id', 'sf-status': 'status', 'sf-from': 'date_from', 'sf-to': 'date_to' }[e.target.id];
    if (m) { sf[m] = e.target.value; paint(); }
  });
  $('#new-class', root).addEventListener('click', () => classForm());
  $('#new-session', root).addEventListener('click', () => sessionForm());
  await paint();
}
