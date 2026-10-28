import { api } from '../api.js';
import { h, setHTML, $, fmtDate, fmtDateTime } from '../util.js';
import { icon } from '../icons.js';
import { toast, empty, callout, confirmDialog, decisionBadge, withBusy } from '../ui.js';

const REVIEW_STATUS = { pending: ['b-amber', 'Pending'], confirmed: ['b-teal', 'Confirmed'], rejected: ['b-red', 'Rejected'], unknown: ['b-slate', 'Marked unknown'] };

export default async function render(root, ctx) {
  let view = ctx.params.get('view') === 'decided' ? 'decided' : 'pending';
  setHTML(root, h`
    <div class="page-head"><div><h1>Review queue</h1><p>Uncertain recognition results wait here. Nothing is recorded until you decide.</p></div></div>
    <div class="tabs" style="margin-bottom:16px"><button class="tab" data-v="pending">Pending <span id="pcount"></span></button><button class="tab" data-v="decided">Decided</button></div>
    <div id="list"></div>`);

  async function load() {
    root.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.v === view));
    let r;
    try { r = await api.get(`/api/review?status=${view}`); } catch (e) { setHTML($('#list', root), callout('error', e.message)); return; }
    $('#pcount', root).textContent = r.pending_total ? `(${r.pending_total})` : '';
    ctx.refreshPending?.();
    if (!r.items.length) { setHTML($('#list', root), h`<section class="card">${empty({ icon: 'inbox', title: view === 'pending' ? 'Nothing to review' : 'No decisions yet', text: view === 'pending' ? 'Cases appear here when recognition is uncertain, for example a match below the automatic-accept threshold.' : 'Decided cases are listed here.' })}</section>`); return; }
    setHTML($('#list', root), h`<div class="stack">${r.items.map(card)}</div>`);
    r.items.filter((e) => e.has_thumbnail).forEach(loadThumb);
  }
  async function loadThumb(e) {
    try {
      const res = await fetch(`/api/review/${e.id}/thumbnail`, { credentials: 'same-origin' }); if (!res.ok) return;
      const url = URL.createObjectURL(await res.blob()); const el = root.querySelector(`[data-thumb="${e.id}"]`);
      if (el) { el.innerHTML = ''; const img = new Image(); img.alt = 'Captured face awaiting review'; img.src = url; img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:12px;transform:scaleX(-1)'; el.appendChild(img); }
    } catch {}
  }
  function card(e) {
    const st = REVIEW_STATUS[e.review_status] || ['b-slate', e.review_status];
    return h`<section class="card" data-case="${e.id}"><div class="review-card">
      <div class="thumb" data-thumb="${e.id}">${e.has_thumbnail ? 'Loading…' : 'No image kept'}</div>
      <div>
        <div class="row spread" style="align-items:flex-start"><div>
          <h3>${e.student_name ? h`${e.student_name} <span class="muted small">${e.student_id}</span>` : 'No candidate student'}</h3>
          <p class="small muted">${e.course_code} · Sec ${e.section} · ${fmtDate(e.session_date)} · ${fmtDateTime(e.timestamp)}</p></div>
          <div class="row">${decisionBadge(e.decision, e.decision_label)}<span class="badge ${st[0]}">${st[1]}</span></div></div>
        <div class="callout info" style="margin:12px 0">${icon('info')}<div><b>Why this needs review:</b> ${e.reason}</div></div>
        <dl class="kv" style="grid-template-columns:200px 1fr">
          <dt><span class="tip" title="Cosine similarity between the camera face and the enrolled template (-1 to 1). It is a distance-style score, not a probability.">Similarity score</span></dt><dd>${e.similarity == null ? '—' : e.similarity.toFixed(3)}${e.runner_up_similarity != null ? h` <span class="muted small">(next best ${e.runner_up_similarity.toFixed(3)})</span>` : ''}</dd>
          <dt>Image quality</dt><dd>${e.quality_status === 'ok' ? 'Passed quality checks' : e.quality_status}</dd>
          <dt>Session status</dt><dd>${e.session_status}</dd>${e.reviewed_at ? h`<dt>Decided</dt><dd>${fmtDateTime(e.reviewed_at)}</dd>` : ''}</dl>
        ${e.review_status === 'pending' ? h`<div class="row" style="margin-top:14px">
          <button class="btn primary" data-do="confirm" data-id="${e.id}" ${e.student_pk ? '' : 'disabled'}>${icon('check')} Confirm candidate</button>
          <button class="btn danger" data-do="reject" data-id="${e.id}">${icon('x')} Reject candidate</button>
          <button class="btn" data-do="unknown" data-id="${e.id}">${icon('userx')} Mark as unknown</button>
          <button class="btn ghost" data-do="keep_pending" data-id="${e.id}">${icon('clock')} Keep pending</button></div>
          ${e.session_status !== 'active' ? h`<p class="hint" style="margin-top:8px">The session is ${e.session_status}. Confirming requires an active session; reopen it in Classes & Sessions first.</p>` : ''}` : ''}
      </div></div></section>`;
  }

  const TEXT = {
    confirm: (e) => ({ title: `Confirm ${e.student_name}?`, message: 'This records attendance after re-checking that the session is active, the student is active, and no record exists yet.', confirmText: 'Confirm and record' }),
    reject: () => ({ title: 'Reject this candidate?', message: 'No attendance is recorded. The captured face thumbnail is deleted.', confirmText: 'Reject', danger: true }),
    unknown: () => ({ title: 'Mark as unknown identity?', message: 'No attendance is recorded. The captured face thumbnail is deleted.', confirmText: 'Mark unknown' }),
  };
  root.addEventListener('click', async (ev) => {
    const t = ev.target.closest('.tab'); if (t) { view = t.dataset.v; load(); return; }
    const b = ev.target.closest('[data-do]'); if (!b) return;
    const id = b.dataset.id, action = b.dataset.do, card_ = root.querySelector(`[data-case="${id}"]`);
    const name = card_.querySelector('h3').firstChild?.textContent?.trim();
    if (TEXT[action] && !(await confirmDialog(TEXT[action]({ student_name: name })))) return;
    try {
      const r = await withBusy(b, () => api.post(`/api/review/${id}/decision`, { action }), 'Saving…');
      toast(r.message, action === 'confirm' ? 'ok' : 'warn'); load();
    } catch (e) { toast(e.message, 'error'); load(); }
  });
  await load();
  const timer = setInterval(() => load().catch(() => {}), 20000); // controlled periodic refresh
  return () => clearInterval(timer);
}
