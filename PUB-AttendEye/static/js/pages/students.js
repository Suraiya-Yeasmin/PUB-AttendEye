import { api } from '../api.js';
import { h, setHTML, $, $$, debounce, qs, fmtDate, fmtDateTime, initials } from '../util.js';
import { icon } from '../icons.js';
import { toast, empty, callout, confirmDialog, formModal, openModal, menu, consentBadge, withBusy } from '../ui.js';

const FIELDS = [
  { name: 'student_id', label: 'Student ID', required: true, maxlength: 32, pattern: /^[A-Za-z0-9._/-]{3,32}$/, patternMsg: 'Use 3-32 letters, digits, dot, dash, slash or underscore.', hint: 'Unique across the university.' },
  { name: 'full_name', label: 'Full name', required: true, maxlength: 120 },
  { name: 'department', label: 'Department', required: true, maxlength: 80 },
  { name: 'section', label: 'Section', required: true, maxlength: 32 },
  { name: 'email', label: 'Email (optional)', type: 'email', maxlength: 254, full: true },
];

export default async function render(root, ctx) {
  const f = { q: '', status: '', department: '', section: '', enrollment: '', page: 1, page_size: 20 };
  let data = { items: [], total: 0, departments: [], sections: [] };

  setHTML(root, h`
    <div class="page-head"><div><h1>Students</h1><p>Manage the student register, enrollment status and biometric consent.</p></div>
      <div class="row"><button class="btn primary" id="add">${icon('userplus')} Add student</button></div></div>
    <section class="card">
      <div class="toolbar">
        <div class="input-wrap grow">${icon('search')}<input class="input" id="q" type="search" placeholder="Search by name or student ID" aria-label="Search students"></div>
        <select class="select" id="f-status" aria-label="Status"><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select>
        <select class="select" id="f-enrollment" aria-label="Face enrollment"><option value="">All enrollment</option><option value="enrolled">Face enrolled</option><option value="not_enrolled">Not enrolled</option><option value="declined">Declined biometrics</option></select>
        <select class="select" id="f-department" aria-label="Department"></select>
        <select class="select" id="f-section" aria-label="Section"></select>
      </div>
      <div id="table"></div>
    </section>`);

  async function load() {
    try { data = await api.get('/api/students' + qs(f)); } catch (e) { setHTML($('#table', root), callout('error', e.message)); return; }
    fillFilters(); paint();
  }
  function fillFilters() {
    const opt = (all, list, cur) => h`<option value="">${all}</option>${list.map((x) => h`<option value="${x}" ${x === cur ? 'selected' : ''}>${x}</option>`)}`;
    setHTML($('#f-department', root), opt('All departments', data.departments, f.department));
    setHTML($('#f-section', root), opt('All sections', data.sections, f.section));
  }
  function paint() {
    const t = $('#table', root);
    const filtered = f.q || f.status || f.department || f.section || f.enrollment;
    if (!data.items.length) {
      setHTML(t, filtered
        ? empty({ icon: 'search', title: 'No students match', text: 'Try different search words or clear the filters.' })
        : empty({ icon: 'users', title: 'No students yet', text: 'Add your first student to begin. Face enrollment comes after the student has given consent.', action: h`<button class="btn primary" data-act="add">${icon('userplus')} Add student</button>` }));
      return;
    }
    const pages = Math.max(1, Math.ceil(data.total / f.page_size));
    setHTML(t, h`<div class="table-wrap"><table class="t"><thead><tr><th>Student</th><th>Department</th><th>Section</th><th>Status</th><th>Face enrollment</th><th>Added</th><th class="right"><span class="sr-only">Actions</span></th></tr></thead><tbody>
      ${data.items.map((s) => h`<tr>
        <td><div class="row"><div class="avatar" style="width:34px;height:34px;font-size:12px">${initials(s.full_name)}</div><div><b>${s.full_name}</b><div class="sub">${s.student_id}</div></div></div></td>
        <td>${s.department}</td><td>${s.section}</td>
        <td><span class="badge ${s.status === 'active' ? 'b-teal' : 'b-slate'}">${s.status === 'active' ? 'Active' : 'Inactive'}</span></td>
        <td>${consentBadge(s)}</td><td class="nowrap">${fmtDate(s.created_at)}</td>
        <td class="right">${menu([
          { action: 'view', id: s.id, label: 'View details', icon: 'file' },
          { action: 'edit', id: s.id, label: 'Edit', icon: 'edit' },
          { action: 'enroll', id: s.id, label: s.face_enrolled ? 'Re-enroll face' : 'Enroll face', icon: 'faceid' },
          ...(s.face_enrolled ? [{ action: 'deltpl', id: s.id, label: 'Remove face template', icon: 'trash', danger: true }] : (s.biometric_consent !== 'declined' ? [{ action: 'decline', id: s.id, label: 'Record: declined biometrics', icon: 'userx' }] : [])),
          '-',
          s.status === 'active' ? { action: 'deactivate', id: s.id, label: 'Deactivate', icon: 'stop', danger: true } : { action: 'activate', id: s.id, label: 'Reactivate', icon: 'refresh' },
        ])}</td></tr>`)}</tbody></table></div>
      <div class="t-foot"><span>Showing ${(f.page - 1) * f.page_size + 1}-${Math.min(f.page * f.page_size, data.total)} of ${data.total}</span>
        <div class="row"><button class="btn sm" data-page="${f.page - 1}" ${f.page <= 1 ? 'disabled' : ''}>${icon('chevleft', 'sm')} Previous</button><span>Page ${f.page} / ${pages}</span><button class="btn sm" data-page="${f.page + 1}" ${f.page >= pages ? 'disabled' : ''}>Next ${icon('chevright', 'sm')}</button></div></div>`);
  }

  // ---------------- modals ----------------
  function addEdit(student) {
    formModal({
      title: student ? 'Edit student' : 'Add student', fields: FIELDS, values: student || {}, submitText: student ? 'Save changes' : 'Add student',
      onSubmit: async (v) => {
        const body = { ...v, email: v.email || null };
        if (student) await api.put(`/api/students/${student.id}`, body); else await api.post('/api/students', body);
        toast(student ? 'Student updated.' : 'Student added.'); load();
      },
    });
  }
  async function view(pk) {
    let s; try { s = await api.get(`/api/students/${pk}`); } catch (e) { toast(e.message, 'error'); return; }
    openModal({ title: s.full_name, body: h`<dl class="kv">
      <dt>Student ID</dt><dd>${s.student_id}</dd><dt>Department</dt><dd>${s.department}</dd><dt>Section</dt><dd>${s.section}</dd><dt>Email</dt><dd>${s.email || '—'}</dd>
      <dt>Status</dt><dd>${s.status}</dd><dt>Biometric status</dt><dd>${consentBadge(s)}${s.face_enrolled ? h` <span class="small muted">${s.enrolled_samples} samples, enrolled ${fmtDateTime(s.template_created_at)}</span>` : ''}</dd>
      <dt>Classes</dt><dd>${s.classes.length ? s.classes.map((c) => `${c.code} (Sec ${c.section})`).join(', ') : 'Not on any class roster'}</dd>
      <dt>Attendance records</dt><dd>${s.attendance_total}</dd><dt>Added</dt><dd>${fmtDateTime(s.created_at)}</dd></dl>
      <p class="hint" style="margin-top:14px">Face templates are encrypted on the server and are never shown or downloaded.</p>`,
      footer: h`<button class="btn" data-close>Close</button>` });
  }
  async function act(action, pk) {
    const s = data.items.find((x) => String(x.id) === String(pk));
    if (action === 'add') return addEdit();
    if (!s) return;
    if (action === 'view') return view(pk);
    if (action === 'edit') return addEdit(s);
    if (action === 'enroll') return ctx.navigate(`#/enroll?student=${s.id}`);
    try {
      if (action === 'deactivate') {
        if (!(await confirmDialog({ title: `Deactivate ${s.full_name}?`, message: 'The student will no longer be matched by the camera or offered for new attendance. Existing records are kept.', confirmText: 'Deactivate', danger: true }))) return;
        await api.post(`/api/students/${pk}/deactivate`); toast('Student deactivated.');
      } else if (action === 'activate') { await api.post(`/api/students/${pk}/activate`); toast('Student reactivated.'); }
      else if (action === 'deltpl') {
        if (!(await confirmDialog({ title: 'Remove face template?', message: `This permanently deletes the stored face template of ${s.full_name}. Camera attendance will no longer work for them until they consent and enroll again. Use manual check-in meanwhile.`, confirmText: 'Delete template', danger: true }))) return;
        await api.del(`/api/students/${pk}/template`); toast('Face template deleted and consent marked as withdrawn.');
      } else if (action === 'decline') {
        if (!(await confirmDialog({ title: 'Record that biometrics were declined?', message: `${s.full_name} will be marked as not consenting. They can still be marked present manually by the teacher.`, confirmText: 'Record' }))) return;
        await api.post(`/api/students/${pk}/consent`, { consent: 'declined' }); toast('Recorded. Use manual check-in for this student.');
      }
      load(); ctx.refreshPending?.();
    } catch (e) { toast(e.message, 'error'); }
  }

  // ---------------- events ----------------
  $('#add', root).addEventListener('click', () => addEdit());
  const reload = () => { f.page = 1; load(); };
  $('#q', root).addEventListener('input', debounce((e) => { f.q = e.target.value.trim(); reload(); }, 250));
  for (const k of ['status', 'enrollment', 'department', 'section']) $(`#f-${k}`, root).addEventListener('change', (e) => { f[k] = e.target.value; reload(); });
  root.addEventListener('click', (e) => {
    const b = e.target.closest('[data-action],[data-act],[data-page]'); if (!b) return;
    if (b.dataset.page) { f.page = Number(b.dataset.page); load(); return; }
    act(b.dataset.action || b.dataset.act, b.dataset.id);
  });
  await load();
  if (ctx.params.get('new') === '1') addEdit();
}
