import { api, download } from '../api.js';
import { h, setHTML, $, qs, fmtDate, pct } from '../util.js';
import { icon } from '../icons.js';
import { toast, empty, callout, statCard, sessionBadge, withBusy } from '../ui.js';
import { bars, line, COLORS } from '../charts.js';

export default async function render(root, ctx) {
  const f = { class_id: '', date_from: '', date_to: '' };
  const classes = (await api.get('/api/classes')).items;
  let summary = null;

  setHTML(root, h`
    <div class="page-head"><div><h1>Reports & analytics</h1><p>Figures are calculated from recorded attendance only. Percentages need a class roster; sessions without one show "—".</p></div></div>
    <section class="card" style="margin-bottom:18px"><div class="toolbar" style="border:0">
      <select class="select" id="class_id" aria-label="Class"><option value="">All classes</option>${classes.map((c) => h`<option value="${c.id}">${c.code} · Sec ${c.section}</option>`)}</select>
      <label class="small muted" for="date_from">From</label><input class="input" style="width:auto" type="date" id="date_from"><label class="small muted" for="date_to">To</label><input class="input" style="width:auto" type="date" id="date_to">
      <button class="btn" id="clear">Clear filters</button></div></section>
    <div id="out"></div>`);

  async function load() {
    const out = $('#out', root);
    try { summary = await api.get('/api/reports/summary' + qs(f)); } catch (e) { setHTML(out, callout('error', e.message)); return; }
    const s = summary, t = s.totals;
    if (!s.sessions.length) { setHTML(out, h`<section class="card">${empty({ icon: 'chart', title: 'No data for this selection', text: 'Reports include active and completed sessions. Start a session and record attendance, or widen the filters.' })}</section>`); return; }
    const withPct = s.sessions.filter((r) => r.percentage != null);
    setHTML(out, h`
      <div class="stat-grid" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:18px">
        ${statCard({ label: 'Sessions', value: t.sessions, sub: 'active + completed', tone: 'blue', ic: 'calendar' })}
        ${statCard({ label: 'Present check-ins', value: t.present, sub: 'present or late', tone: 'teal', ic: 'checkcircle' })}
        ${statCard({ label: 'Average attendance', value: t.average_percentage == null ? '—' : pct(t.average_percentage), sub: 'sessions with a roster', tone: 'indigo', ic: 'chart' })}
        ${statCard({ label: 'Pending review', value: t.pending_review, sub: t.pending_review ? 'not counted as present or absent' : 'no open cases', tone: 'amber', ic: 'inbox', href: '#/review' })}</div>
      <div class="grid g2" style="margin-bottom:18px">
        <section class="card"><div class="card-head"><h2>Attendance trend</h2><span class="small muted">% of roster present, by session date</span></div><div class="card-body">${withPct.length ? line(withPct.map((r) => ({ label: fmtDate(r.session_date).replace(/, \d{4}/, ''), value: r.percentage }))) : empty({ icon: 'chart', title: 'No percentages yet', text: 'Assign a roster to the class to calculate percentages.' })}</div></section>
        <section class="card"><div class="card-head"><h2>Session comparison</h2><span class="small muted">latest ${Math.min(s.sessions.length, 12)}</span></div><div class="card-body">${withPct.length ? bars(withPct.slice(-12).map((r) => ({ label: `${r.course_code} ${fmtDate(r.session_date).replace(/, \d{4}/, '')}`, value: r.percentage })), { color: COLORS.navy }) : empty({ icon: 'chart', title: 'Nothing to compare yet' })}</div></section></div>
      <section class="card" style="margin-bottom:18px"><div class="card-head"><h2>Class summaries</h2><button class="btn sm" data-export="sessions">${icon('download', 'sm')} Export session summary CSV</button></div><div class="card-body flush"><div class="table-wrap"><table class="t"><thead><tr><th>Course</th><th>Section</th><th>Sessions</th><th>Roster</th><th>Average attendance</th><th></th></tr></thead><tbody>
        ${s.classes.map((c) => h`<tr><td><b>${c.course_code}</b><div class="sub">${c.course_name}</div></td><td>${c.section}</td><td>${c.sessions}</td><td>${c.roster_size || '—'}</td><td>${c.average_percentage == null ? '—' : pct(c.average_percentage)}</td>
          <td class="right"><button class="btn sm" data-students="${c.class_id}">Student breakdown</button></td></tr>`)}</tbody></table></div></div></section>
      <section class="card" style="margin-bottom:18px"><div class="card-head"><h2>Session attendance summary</h2></div><div class="card-body flush"><div class="table-wrap"><table class="t"><thead><tr><th>Date</th><th>Course</th><th>Status</th><th>Roster</th><th>Present</th><th>Excused</th><th><span class="tip" title="Face matches still waiting for teacher review. Not counted as present or absent.">Pending review</span></th><th>Absent</th><th>Attendance</th><th></th></tr></thead><tbody>
        ${[...s.sessions].reverse().map((r) => h`<tr><td class="nowrap">${fmtDate(r.session_date)}</td><td><b>${r.course_code}</b> <span class="muted small">Sec ${r.section}</span></td><td>${sessionBadge(r.status)}</td><td>${r.roster_size || '—'}</td><td>${r.present}</td><td>${r.excused}</td><td>${r.pending_review ? h`<span class="badge b-amber">${r.pending_review}</span>` : 0}</td><td>${r.absent ?? '—'}</td><td>${r.percentage == null ? '—' : pct(r.percentage)}</td>
          <td class="right"><button class="btn sm" data-export="session" data-id="${r.session_id}">${icon('download', 'sm')} CSV</button></td></tr>`)}</tbody></table></div></div></section>
      <section class="card" id="students-card" hidden></section>
      <section class="card" style="margin-top:18px"><div class="card-head"><h2>How these numbers are defined</h2></div><div class="card-body"><dl class="kv" style="grid-template-columns:140px 1fr">${Object.entries(s.definitions).map(([k, v]) => h`<dt>${k.replace('_', ' ')}</dt><dd class="small">${v}</dd>`)}</dl></div></section>`);
  }

  async function studentBreakdown(classId) {
    const card = $('#students-card', root);
    try {
      const r = await api.get(`/api/reports/class/${classId}/students` + qs({ date_from: f.date_from, date_to: f.date_to }));
      card.hidden = false;
      setHTML(card, h`<div class="card-head"><h2>Student attendance - ${r.class.code} (Sec ${r.class.section})</h2><button class="btn sm" data-export="class_students" data-id="${classId}">${icon('download', 'sm')} Export CSV</button></div>
        <div class="card-body flush">${r.students.length ? h`<div class="table-wrap"><table class="t"><thead><tr><th>Student</th><th>Sessions</th><th>Present</th><th>Excused</th><th>Absent</th><th>Attendance</th></tr></thead><tbody>
        ${r.students.map((x) => h`<tr><td><b>${x.full_name}</b><div class="sub">${x.student_id}</div></td><td>${x.sessions}</td><td>${x.present}</td><td>${x.excused}</td><td>${x.absent}</td><td>${x.percentage == null ? '—' : h`<div class="row"><div class="progress" style="width:90px"><i style="width:${x.percentage}%;background:${x.percentage < 75 ? 'var(--amber-500)' : 'var(--teal-500)'}"></i></div>${pct(x.percentage)}</div>`}</td></tr>`)}</tbody></table></div>` : empty({ icon: 'users', title: 'This class has no roster', text: 'Add students under Classes & Sessions → Manage roster.' })}</div>`);
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) { toast(e.message, 'error'); }
  }

  async function exportCsv(kind, id, btn) {
    const params = { kind, date_from: f.date_from, date_to: f.date_to, class_id: kind === 'class_students' ? id : f.class_id };
    if (kind === 'session') params.session_id = id;
    try {
      const r = await withBusy(btn, () => download('/api/reports/export' + qs(params), 'report.csv'), 'Exporting…');
      toast(r.rows ? `Exported ${r.rows} row(s) to ${r.name}.` : 'The export contains only headers: there are no rows for this selection.', r.rows ? 'ok' : 'warn');
    } catch (e) { toast(e.message, 'error'); }
  }

  root.addEventListener('click', (e) => {
    const x = e.target.closest('[data-export]'); if (x) return exportCsv(x.dataset.export, x.dataset.id, x);
    const s = e.target.closest('[data-students]'); if (s) studentBreakdown(s.dataset.students);
  });
  for (const k of ['class_id', 'date_from', 'date_to']) $('#' + k, root).addEventListener('change', (e) => { f[k] = e.target.value; load(); });
  $('#clear', root).addEventListener('click', () => { Object.keys(f).forEach((k) => { f[k] = ''; $('#' + k, root).value = ''; }); load(); });
  await load();
}
