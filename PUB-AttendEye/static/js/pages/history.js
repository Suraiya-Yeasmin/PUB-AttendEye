import { api, download } from '../api.js';
import { h, setHTML, $, $$, debounce, qs, fmtDate, fmtDateTime } from '../util.js';
import { icon } from '../icons.js';
import { toast, empty, callout, confirmDialog, formModal, openModal, attBadge, methodLabel, reviewLabel, withBusy } from '../ui.js';

const COLS = [['student_id', 'Student ID'], ['student_name', 'Name'], ['course', 'Course'], ['session_date', 'Session date'], ['timestamp', 'Recorded at'], ['method', 'Method'], ['status', 'Status']];

export default async function render(root, ctx) {
  const f = { class_id: '', session_id: ctx.params.get('session') || '', q: '', status: '', method: '', date_from: '', date_to: '', sort: 'timestamp', direction: 'desc', page: 1, page_size: 25 };
  let data = { items: [], total: 0 }, classes = [], sessions = [];
  [classes, sessions] = await Promise.all([api.get('/api/classes').then((r) => r.items), api.get('/api/sessions?limit=300').then((r) => r.items)]);

  setHTML(root, h`
    <div class="page-head"><div><h1>Attendance history</h1><p>Search every recorded attendance entry. Corrections are saved with an audit trail.</p></div><div class="row"><button class="btn" id="export">${icon('download')} Export CSV (current filters)</button></div></div>
    <section class="card"><div class="toolbar">
      <div class="input-wrap grow">${icon('search')}<input class="input" id="q" type="search" placeholder="Search student name or ID" aria-label="Search student"></div>
      <select class="select" id="class_id" aria-label="Class"></select><select class="select" id="session_id" aria-label="Session"></select>
      <select class="select" id="status" aria-label="Status"><option value="">All statuses</option><option value="present">Present</option><option value="late">Late</option><option value="excused">Excused</option></select>
      <select class="select" id="method" aria-label="Method"><option value="">All methods</option><option value="face">Face recognition</option><option value="face_review">Face + review</option><option value="manual">Manual</option></select>
      <input class="input" style="width:auto" type="date" id="date_from" aria-label="From date"><input class="input" style="width:auto" type="date" id="date_to" aria-label="To date"></div>
      <div id="table"></div></section>`);

  function fillSelects() {
    setHTML($('#class_id', root), h`<option value="">All classes</option>${classes.map((c) => h`<option value="${c.id}" ${String(c.id) === f.class_id ? 'selected' : ''}>${c.code} · Sec ${c.section}</option>`)}`);
    const list = sessions.filter((s) => !f.class_id || String(s.class_id) === f.class_id);
    setHTML($('#session_id', root), h`<option value="">All sessions</option>${list.map((s) => h`<option value="${s.id}" ${String(s.id) === String(f.session_id) ? 'selected' : ''}>${s.course_code} · ${fmtDate(s.session_date)} ${s.start_time}</option>`)}`);
  }
  async function load() {
    try { data = await api.get('/api/attendance' + qs(f)); } catch (e) { setHTML($('#table', root), callout('error', e.message)); return; }
    paint();
  }
  function paint() {
    const el = $('#table', root);
    if (!data.items.length) { setHTML(el, empty({ icon: 'history', title: 'No attendance records', text: 'Nothing matches these filters. Records appear after a session has attendance.' })); return; }
    const pages = Math.max(1, Math.ceil(data.total / f.page_size));
    const th = ([k, label]) => h`<th class="sortable" data-sort="${k}" aria-sort="${f.sort === k ? (f.direction === 'asc' ? 'ascending' : 'descending') : 'none'}">${label}${f.sort === k ? (f.direction === 'asc' ? ' ▲' : ' ▼') : ''}</th>`;
    setHTML(el, h`<div class="table-wrap"><table class="t"><thead><tr>${COLS.map(th)}<th>Review</th><th></th></tr></thead><tbody>
      ${data.items.map((a) => h`<tr><td>${a.student_id}</td><td><b>${a.student_name}</b></td><td>${a.course_code}<div class="sub">Sec ${a.section}</div></td><td class="nowrap">${fmtDate(a.session_date)}</td><td class="nowrap">${fmtDateTime(a.timestamp)}</td>
        <td>${methodLabel(a.method)}</td><td>${attBadge(a.status)}${a.corrected ? h` <span class="badge plain b-slate" title="Corrected by a teacher">edited</span>` : ''}</td><td>${reviewLabel(a.review_status)}</td>
        <td class="right"><button class="btn sm" data-detail="${a.id}">Details</button></td></tr>`)}</tbody></table></div>
      <div class="t-foot"><span>${data.total} record(s)</span><div class="row"><button class="btn sm" data-page="${f.page - 1}" ${f.page <= 1 ? 'disabled' : ''}>${icon('chevleft', 'sm')} Previous</button><span>Page ${f.page} / ${pages}</span><button class="btn sm" data-page="${f.page + 1}" ${f.page >= pages ? 'disabled' : ''}>Next ${icon('chevright', 'sm')}</button></div></div>`);
  }

  async function detail(id) {
    let a; try { a = await api.get(`/api/attendance/${id}`); } catch (e) { toast(e.message, 'error'); return; }
    const m = openModal({
      title: `${a.student_name} · ${a.course_code}`,
      body: h`<dl class="kv"><dt>Student ID</dt><dd>${a.student_id}</dd><dt>Course</dt><dd>${a.course_code} · ${a.course_name} (Sec ${a.section})</dd><dt>Session date</dt><dd>${fmtDate(a.session_date)}</dd>
        <dt>Recorded at</dt><dd>${fmtDateTime(a.timestamp)}</dd><dt>Verification method</dt><dd>${methodLabel(a.method)}</dd><dt>Status</dt><dd>${attBadge(a.status)}</dd><dt>Review status</dt><dd>${reviewLabel(a.review_status)}</dd>
        <dt><span class="tip" title="Cosine similarity at recognition time; not a probability.">Similarity score</span></dt><dd>${a.similarity == null ? 'Not applicable' : a.similarity.toFixed(3)}</dd>${a.note ? h`<dt>Note</dt><dd>${a.note}</dd>` : ''}</dl>
        <h3 style="margin:18px 0 6px">Audit trail</h3>${a.audit.length ? a.audit.map((l) => h`<div class="list-item"><div class="dot tone-slate">${icon('clock', 'sm')}</div><div><b>${l.action.replace(/_/g, ' ')}</b> by ${l.by || 'system'}<div class="small muted">${fmtDateTime(l.timestamp)}${l.detail ? ' · ' + prettyDetail(l.detail) : ''}</div></div></div>`) : h`<p class="muted small">No corrections have been made to this record.</p>`}`,
      footer: h`<button class="btn" data-close>Close</button><button class="btn danger" data-remove>${icon('trash')} Remove record</button><button class="btn primary" data-correct>${icon('edit')} Correct status</button>`,
      onMount: (m) => {
        m.$('[data-correct]').addEventListener('click', () => { m.close(); correct(a); });
        m.$('[data-remove]').addEventListener('click', () => { m.close(); remove(a); });
      },
    });
  }
  const prettyDetail = (d) => { try { return Object.entries(JSON.parse(d)).map(([k, v]) => `${k}: ${v}`).join(', '); } catch { return d; } };
  function correct(a) {
    formModal({
      title: 'Correct attendance', intro: h`<p class="muted">${a.student_name} · ${a.course_code} · ${fmtDate(a.session_date)}. The change and your note are saved in the audit trail.</p>`,
      fields: [{ name: 'status', label: 'Status', type: 'select', options: ['present', 'late', 'excused'].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) })), default: a.status, full: true }, { name: 'note', label: 'Reason for correction', required: true, maxlength: 300, full: true }],
      submitText: 'Save correction', onSubmit: async (v) => { await api.put(`/api/attendance/${a.id}`, v); toast('Correction saved and logged.'); load(); },
    });
  }
  function remove(a) {
    formModal({
      title: 'Remove attendance record', intro: callout('warn', `${a.student_name} will become absent for this session. The removal is logged.`),
      fields: [{ name: 'reason', label: 'Reason', required: true, maxlength: 300, full: true }], submitText: 'Remove record',
      onSubmit: async (v) => { await api.post(`/api/attendance/${a.id}/remove`, v); toast('Record removed and logged.'); load(); },
    });
  }

  const reload = () => { f.page = 1; load(); };
  $('#q', root).addEventListener('input', debounce((e) => { f.q = e.target.value.trim(); reload(); }));
  for (const k of ['status', 'method', 'date_from', 'date_to']) $('#' + k, root).addEventListener('change', (e) => { f[k] = e.target.value; reload(); });
  $('#class_id', root).addEventListener('change', (e) => { f.class_id = e.target.value; f.session_id = ''; fillSelects(); reload(); });
  $('#session_id', root).addEventListener('change', (e) => { f.session_id = e.target.value; reload(); });
  root.addEventListener('click', (e) => {
    const th = e.target.closest('[data-sort]'); if (th) { const k = th.dataset.sort; f.direction = f.sort === k && f.direction === 'desc' ? 'asc' : 'desc'; f.sort = k; load(); return; }
    const p = e.target.closest('[data-page]'); if (p) { f.page = Number(p.dataset.page); load(); return; }
    const d = e.target.closest('[data-detail]'); if (d) detail(d.dataset.detail);
  });
  $('#export', root).addEventListener('click', async (e) => {
    try { const r = await withBusy(e.currentTarget, () => download('/api/reports/export' + qs({ kind: 'history', class_id: f.class_id, session_id: f.session_id, q: f.q, status: f.status, method: f.method, date_from: f.date_from, date_to: f.date_to }), 'attendance_history.csv'), 'Exporting…');
      toast(r.rows ? `Exported ${r.rows} record(s) to ${r.name}.` : 'The export is empty: no records match these filters.', r.rows ? 'ok' : 'warn'); } catch (ex) { toast(ex.message, 'error'); }
  });
  if (f.session_id) { const s = sessions.find((x) => String(x.id) === String(f.session_id)); if (s) f.class_id = String(s.class_id); }
  fillSelects(); await load();
}
