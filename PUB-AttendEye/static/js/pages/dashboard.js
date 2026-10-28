import { api } from '../api.js';
import { h, setHTML, $, fmtDate, fmtTimeSec, fmtDateTime, pct } from '../util.js';
import { icon } from '../icons.js';
import { statCard, empty, callout, sessionBadge, decisionBadge, confirmDialog, toast, withBusy } from '../ui.js';
import { donut, line, COLORS } from '../charts.js';

export default async function render(root, ctx) {
  let sessionId = ctx.params.get('session') || '';
  async function load() {
    const d = await api.get('/api/dashboard' + (sessionId ? `?session_id=${sessionId}` : ''));
    draw(d);
  }
  function draw(d) {
    const c = d.cards, s = d.selected_session, ov = d.overview;
    const first = ctx.teacher.full_name.replace(/^(dr|prof|professor|mr|mrs|ms|engr)\.?\s+/i, '').split(' ')[0];
    setHTML(root, h`
      <div class="page-head"><div><h1>Welcome back, ${first}</h1><p>${d.empty.no_classes ? 'Set up your first class to begin taking attendance.' : 'Here is what is happening across your classes.'}</p></div>
        <div class="row"><a class="btn" href="#/live">${icon('camera')} Live Attendance</a><a class="btn primary" href="#/classes">${icon('plus')} New session</a></div></div>
      ${d.empty.no_students || d.empty.no_classes ? h`<div style="margin-bottom:18px">${callout('info', h`<b>Getting started:</b> ${d.empty.no_students ? h`<a href="#/students">add students</a>` : ''}${d.empty.no_students && d.empty.no_classes ? ', ' : ''}${d.empty.no_classes ? h`<a href="#/classes">create a class and session</a>` : ''}, then <a href="#/enroll">enroll faces</a> (with consent) to use camera attendance.`)}</div>` : ''}
      <div class="stat-grid">
        ${statCard({ label: 'Enrolled students', value: c.total_students, sub: `${c.face_enrolled} with a face template`, tone: 'blue', ic: 'users', href: '#/students' })}
        ${statCard({ label: 'Present (selected session)', value: c.present ?? '—', sub: s ? `${s.course_code} · ${fmtDate(s.session_date)}` : 'No session yet', tone: 'teal', ic: 'checkcircle', href: s ? `#/history?session=${s.id}` : '#/classes' })}
        ${statCard({ label: 'Absent (selected session)', value: c.absent ?? '—', sub: s ? (s.roster_size ? `of ${s.roster_size} on roster` : 'No roster assigned') : 'No session yet', tone: 'red', ic: 'userx', href: s ? '#/classes' : undefined })}
        ${statCard({ label: 'Pending teacher reviews', value: c.pending_reviews, sub: c.pending_reviews ? 'Needs your decision' : 'Nothing waiting', tone: 'amber', ic: 'inbox', href: '#/review' })}
        ${statCard({ label: 'Unknown identities', value: c.unknown_detected, sub: 'events in selected session', tone: 'slate', ic: 'alert' })}
        ${statCard({ label: 'Duplicates prevented', value: c.duplicates_prevented, sub: 'in selected session', tone: 'indigo', ic: 'shield' })}
      </div>
      <div class="row small muted" style="margin:-4px 0 16px;gap:22px;flex-wrap:wrap" aria-label="At a glance"><span><b>${d.glance.classes}</b> ${d.glance.classes === 1 ? 'class' : 'classes'}</span><span><b>${d.glance.sessions}</b> ${d.glance.sessions === 1 ? 'session' : 'sessions'} (${d.glance.sessions_today} today)</span><span><b>${d.glance.checkins_today}</b> ${d.glance.checkins_today === 1 ? 'check-in' : 'check-ins'} recorded today</span><span class="tip" title="Absent = roster students with no record and no pending review case. Same definition as Reports.">How absent is counted</span></div>
      <div class="grid g-main">
        <div class="stack">
          <section class="card" aria-labelledby="active-h"><div class="card-head"><h2 id="active-h">Current attendance session</h2>${s ? sessionBadge(s.status) : ''}</div><div class="card-body">${sessionPanel(d)}</div></section>
          <section class="card"><div class="card-head"><h2>Attendance trend across sessions</h2><span class="small muted">% of roster present</span></div><div class="card-body">${d.trend.filter((t) => t.percentage != null).length ? line(d.trend.map((t) => ({ label: t.label, value: t.percentage }))) : empty({ icon: 'chart', title: 'No trend yet', text: 'Trends appear after sessions with a class roster have recorded attendance.' })}</div></section>
          <section class="card"><div class="card-head"><h2>Recent sessions</h2><a href="#/classes" class="small">View all</a></div><div class="card-body flush">${recentTable(d.recent_sessions)}</div></section>
        </div>
        <div class="stack">
          <section class="card"><div class="card-head"><h2>Attendance overview</h2></div><div class="card-body">${ov ? donut([
            { label: 'Present', value: ov.present - ov.late, color: COLORS.teal }, { label: 'Late', value: ov.late, color: COLORS.amber },
            { label: 'Excused', value: ov.excused, color: COLORS.blue }, { label: 'Absent', value: ov.absent, color: COLORS.red }], { center: ov.roster_size ? pct(Math.round(100 * ov.present / ov.roster_size)) : String(ov.present), sub: ov.roster_size ? 'present' : 'checked in' }) : empty({ icon: 'chart', title: 'No session selected', text: 'Create or start a session to see its overview.' })}
            ${ov && !ov.roster_size ? h`<p class="hint" style="margin-top:10px">This class has no roster, so absences cannot be calculated. Add students under Classes & Sessions.</p>` : ''}</div></section>
          <section class="card"><div class="card-head"><h2>Quick actions</h2></div><div class="card-body"><div class="grid g2" style="gap:10px">
            ${[['userplus', 'Add student', '#/students?new=1'], ['faceid', 'Enroll a face', '#/enroll'], ['camera', 'Take attendance', '#/live'], ['inbox', 'Review queue', '#/review'], ['download', 'Export CSV', '#/reports'], ['gauge', 'Evaluate system', '#/evaluation']].map(([i, t, href]) => h`<a class="btn" href="${href}" style="justify-content:flex-start">${icon(i)} ${t}</a>`)}</div></div></section>
          <section class="card"><div class="card-head"><h2>Recent attendance activity</h2></div><div class="card-body">${d.activity.length ? d.activity.map(activityItem) : empty({ icon: 'clock', title: 'No activity yet', text: 'Recognition events for the selected session appear here.' })}</div></section>
        </div>
      </div>`);
    root.querySelector('#start-btn')?.addEventListener('click', onStart);
    root.querySelector('#end-btn')?.addEventListener('click', onEnd);
    root.querySelector('#sess-pick')?.addEventListener('change', (e) => { sessionId = e.target.value; load(); });
  }
  function sessionPanel(d) {
    const s = d.selected_session;
    if (!s && !d.startable_sessions.length) return empty({ icon: 'calendar', title: d.empty.no_classes ? 'No classes yet' : 'No sessions yet', text: d.empty.no_classes ? 'Create a class first, then schedule a session.' : 'Schedule a session to start taking attendance.', action: h`<a class="btn primary" href="#/classes">${icon('plus')} ${d.empty.no_classes ? 'Create class' : 'Create session'}</a>` });
    return h`${s ? h`<div class="row spread" style="align-items:flex-start"><div><h3>${s.course_code} · ${s.course_name}</h3><p class="muted small">Section ${s.section} · ${fmtDate(s.session_date)} · ${s.start_time}–${s.end_time} · ${s.teacher_name}</p></div>
        <select class="select" id="sess-pick" style="max-width:240px" aria-label="Choose session to summarise">${d.recent_sessions.map((r) => h`<option value="${r.id}" ${r.id === s.id ? 'selected' : ''}>${r.course_code} · ${fmtDate(r.session_date)} (${r.status})</option>`)}</select></div>` : ''}
      <div class="row" style="margin-top:16px">
        ${s?.status === 'active' ? h`<a class="btn primary" href="#/live?session=${s.id}">${icon('camera')} Open live attendance</a><button class="btn danger" id="end-btn" data-id="${s.id}">${icon('stop')} End session</button>` : ''}
        ${s?.status !== 'active' && d.startable_sessions.length ? h`<select class="select" id="start-pick" style="max-width:300px" aria-label="Session to start">${d.startable_sessions.map((x) => h`<option value="${x.id}">${x.course_code} · ${fmtDate(x.session_date)} ${x.start_time}</option>`)}</select><button class="btn primary" id="start-btn">${icon('play')} Start session</button>` : ''}
      </div>
      ${s?.status === 'scheduled' ? '' : ''}`;
  }
  async function onStart(e) {
    const id = $('#start-pick').value;
    try { await withBusy(e.currentTarget, () => api.post(`/api/sessions/${id}/start`), 'Starting…'); toast('Session started. Open Live Attendance to scan faces.'); sessionId = id; await load(); }
    catch (ex) { toast(ex.message, 'error'); }
  }
  async function onEnd(e) {
    const id = e.currentTarget.dataset.id;
    if (!(await confirmDialog({ title: 'End this session?', message: 'Attendance can no longer be recorded after the session is closed. You can reopen it later from Classes & Sessions.', confirmText: 'End session', danger: true }))) return;
    try { await api.post(`/api/sessions/${id}/close`); toast('Session closed.'); await load(); } catch (ex) { toast(ex.message, 'error'); }
  }
  await load();
  const timer = setInterval(() => { if (root.contains(document.activeElement) && document.activeElement.tagName === 'SELECT') return; load().catch(() => {}); }, 15000); // controlled periodic refresh
  return () => clearInterval(timer);
}

function activityItem(e) {
  const tone = { accepted: 'tone-teal', needs_review: 'tone-amber', unknown: 'tone-red', duplicate: 'tone-blue' }[e.decision] || 'tone-slate';
  const ic = { accepted: 'checkcircle', needs_review: 'inbox', unknown: 'userx', duplicate: 'shield' }[e.decision] || 'info';
  return h`<div class="event"><span class="dot ${tone}">${icon(ic)}</span><div style="min-width:0;flex:1"><div class="row spread" style="gap:6px"><b>${e.student_name || 'Unidentified face'}</b><span class="small muted">${fmtTimeSec(e.timestamp)}</span></div><div>${decisionBadge(e.decision, e.decision_label)}</div></div></div>`;
}
function recentTable(rows) {
  if (!rows.length) return empty({ icon: 'calendar', title: 'No sessions yet', text: 'Sessions you schedule will be listed here.' });
  return h`<div class="table-wrap"><table class="t"><thead><tr><th>Course</th><th>Date</th><th>Time</th><th>Present</th><th>Status</th></tr></thead><tbody>${rows.map((r) => h`<tr><td><b>${r.course_code}</b><div class="sub">Section ${r.section}</div></td><td>${fmtDate(r.session_date)}</td><td>${r.start_time}–${r.end_time}</td><td>${r.present_count}${r.roster_size ? ` / ${r.roster_size}` : ''}</td><td>${sessionBadge(r.status)}</td></tr>`)}</tbody></table></div>`;
}
