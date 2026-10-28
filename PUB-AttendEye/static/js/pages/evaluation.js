import { api } from '../api.js';
import { h, setHTML, $, fmtDateTime } from '../util.js';
import { icon } from '../icons.js';
import { toast, empty, callout, statCard, confirmDialog, decisionBadge, withBusy } from '../ui.js';
import { stacked, COLORS } from '../charts.js';
import { Camera, describeCameraError, drawFaces } from '../camera.js';

const OUTCOME = {
  correct_match: ['b-teal', 'Correct match'], correct_rejection: ['b-teal', 'Correctly rejected'], false_accept: ['b-red', 'False accept'],
  false_reject: ['b-red', 'False reject'], sent_to_review: ['b-amber', 'Sent to review'], unusable_quality: ['b-slate', 'Unusable quality'],
};
const NE = h`<span class="muted" title="No labelled samples have been recorded yet">Not evaluated yet</span>`;
const rate = (v) => (v == null ? NE : `${(v * 100).toFixed(1)}%`);

export default async function render(root, ctx) {
  const isAdmin = ctx.teacher.role === 'admin';
  const svc = await api.get('/api/recognition/status').catch((e) => ({ available: false, error: e.message }));
  const students = (await api.get('/api/students?page_size=200&enrollment=enrolled&status=active')).items;
  let cam = null, last = null;

  setHTML(root, h`
    <div class="page-head"><div><h1>System evaluation</h1><p>Measured performance of this installation. Every figure comes from labelled captures you record below; nothing is estimated.</p></div>
      ${isAdmin ? h`<button class="btn" id="reset">${icon('trash')} Clear evaluation data</button>` : ''}</div>
    <div id="summary"></div>
    <div class="grid g2" style="margin-top:18px">
      <section class="card"><div class="card-head"><h2>Record an evaluation sample</h2></div><div class="card-body">
        ${svc.available ? '' : callout('error', 'Recognition service unavailable; samples cannot be recorded.')}
        <p class="hint" style="margin-bottom:10px">One face in view. Tell the system who is really in front of the camera, then capture. The result is stored with the thresholds currently in force.</p>
        <div class="cam" id="cam" style="aspect-ratio:16/10"><video id="video" playsinline muted></video><canvas id="overlay"></canvas><div class="placeholder" id="ph">${icon('camera')}<b>Camera is off</b></div></div>
        <div class="form-grid" style="margin-top:14px">
          <div class="field"><label for="truth">Who is in front of the camera?</label><select class="select" id="truth"><option value="unknown">Someone not enrolled (impostor)</option>${students.map((s) => h`<option value="${s.id}">${s.full_name} (${s.student_id})</option>`)}</select></div>
          <div class="field"><label for="cond">Test condition (optional)</label><input class="input" id="cond" maxlength="80" placeholder="e.g. dim light, glasses, 2 m distance" list="conds"><datalist id="conds"><option value="normal light"><option value="dim light"><option value="backlight"><option value="glasses"><option value="face mask"><option value="head turned"></datalist></div></div>
        <div class="row" style="margin-top:14px"><button class="btn" id="cam-toggle">${icon('camera')} Start camera</button><button class="btn primary" id="capture" disabled>${icon('scan')} Capture & evaluate</button></div>
        <div id="last" style="margin-top:14px"></div></div></section>
      <section class="card"><div class="card-head"><h2>Recent samples</h2></div><div class="card-body flush" id="samples"></div></section>
    </div>`);

  async function load() {
    let s, list;
    try { [s, list] = await Promise.all([api.get('/api/evaluation/summary'), api.get('/api/evaluation/samples?limit=25')]); } catch (e) { setHTML($('#summary', root), callout('error', e.message)); return; }
    const v = (n) => (s.evaluated ? n : NE);
    setHTML($('#summary', root), h`
      ${s.evaluated ? '' : callout('info', h`<b>Not evaluated yet.</b> No labelled samples exist, so accuracy metrics are intentionally blank. Record genuine and impostor captures to measure this installation.`)}
      ${s.small_sample_warning ? callout('warn', `Only ${s.genuine_samples} genuine and ${s.impostor_samples} impostor samples. Treat rates as indicative; a sound evaluation needs many more people, sessions and lighting conditions.`) : ''}
      <div class="stat-grid" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-top:14px">
        ${statCard({ label: 'Evaluation samples', value: s.samples, sub: `${s.genuine_samples} genuine · ${s.impostor_samples} impostor`, tone: 'blue', ic: 'flask' })}
        ${statCard({ label: 'Correct matches', value: v(s.correct_match), sub: 'genuine, right student accepted', tone: 'teal', ic: 'checkcircle' })}
        ${statCard({ label: 'False accepts', value: v(s.false_accept), sub: `rate ${s.false_accept_rate == null ? 'not evaluated yet' : (s.false_accept_rate * 100).toFixed(1) + '% of usable'}`, tone: 'red', ic: 'alert' })}
        ${statCard({ label: 'False rejects', value: v(s.false_reject), sub: `rate ${s.false_reject_rate == null ? 'not evaluated yet' : (s.false_reject_rate * 100).toFixed(1) + '% of genuine'}`, tone: 'amber', ic: 'userx' })}
        ${statCard({ label: 'Unknowns correctly rejected', value: v(s.correct_rejection), sub: 'impostors not accepted', tone: 'teal', ic: 'shield' })}
        ${statCard({ label: 'Review rate', value: s.review_rate == null ? NE : rate(s.review_rate), sub: `${s.sent_to_review} sent to teacher review`, tone: 'amber', ic: 'inbox' })}
        ${statCard({ label: 'Avg processing time', value: s.avg_processing_ms == null ? NE : `${s.avg_processing_ms} ms`, sub: 'detect + quality + match, server side', tone: 'indigo', ic: 'clock' })}
        ${statCard({ label: 'Duplicates prevented', value: s.live.duplicates_prevented, sub: 'live sessions (operational count)', tone: 'indigo', ic: 'shield' })}</div>
      ${s.threshold_sweep.length ? h`<section class="card" style="margin-top:18px"><div class="card-head"><h2>Threshold what-if</h2><span class="small muted">from your ${s.samples} stored samples</span></div><div class="card-body flush"><div class="table-wrap"><table class="t"><thead><tr><th>Accept at similarity ≥</th><th>Correct accepts</th><th>Genuine missed</th><th>False accepts</th><th>False-accept rate</th><th>False-reject rate</th></tr></thead><tbody>
        ${s.threshold_sweep.map((r) => h`<tr><td><b>${r.threshold.toFixed(2)}</b></td><td>${r.genuine_accepted}</td><td>${r.genuine_missed}</td><td>${r.false_accepts}</td><td>${rate(r.false_accept_rate)}</td><td>${rate(r.false_reject_rate)}</td></tr>`)}</tbody></table></div><p class="hint" style="padding:12px 20px">${s.sweep_note}</p></div></section>` : ''}
      <div class="grid g2" style="margin-top:18px">
        <section class="card"><div class="card-head"><h2>Outcome distribution</h2></div><div class="card-body">${s.evaluated ? stacked([
          { label: 'Correct match', value: s.correct_match, color: COLORS.teal }, { label: 'Correct rejection', value: s.correct_rejection, color: '#7ccfc3' }, { label: 'Sent to review', value: s.sent_to_review, color: COLORS.amber },
          { label: 'False accept', value: s.false_accept, color: COLORS.red }, { label: 'False reject', value: s.false_reject, color: '#f08a8a' }, { label: 'Unusable quality', value: s.unusable_quality, color: COLORS.slate }]) : empty({ icon: 'chart', title: 'Not evaluated yet' })}
          ${s.thresholds_used.length ? h`<p class="hint" style="margin-top:12px">Thresholds in the stored samples: ${s.thresholds_used.map((t) => `accept ${t.accept} / review ${t.review}`).join('; ')}.${s.thresholds_vary ? ' Thresholds changed during testing, so the samples are not directly comparable.' : ''}</p>` : ''}</div></section>
        <section class="card"><div class="card-head"><h2>Method & test conditions</h2></div><div class="card-body"><p class="small">${s.method}</p>
          <h3 style="margin:14px 0 6px">Conditions recorded</h3>${Object.keys(s.conditions).length ? h`<ul class="small" style="margin:0;padding-left:18px">${Object.entries(s.conditions).map(([k, n]) => h`<li>${k}: ${n}</li>`)}</ul>` : h`<p class="muted small">None yet.</p>`}
          <h3 style="margin:14px 0 6px">Live operation (not accuracy)</h3><p class="small muted">${s.live.events} recognition events so far: ${s.live.accepted} accepted, ${s.live.needs_review} sent to review, ${s.live.unknown} unknown${s.live.live_review_rate != null ? `; live review rate ${(s.live.live_review_rate * 100).toFixed(1)}%` : ''}${s.live.avg_processing_ms ? `; mean processing ${s.live.avg_processing_ms} ms` : ''}. These have no ground-truth labels, so they are never reported as accuracy.</p></div></section></div>`);
    setHTML($('#samples', root), list.items.length ? h`<div class="table-wrap" style="max-height:420px;overflow:auto"><table class="t"><thead><tr><th>When</th><th>Truth</th><th>Decision</th><th>Outcome</th><th>Score</th></tr></thead><tbody>
      ${list.items.map((x) => h`<tr><td class="nowrap small">${fmtDateTime(x.timestamp)}${x.condition ? h`<div class="sub">${x.condition}</div>` : ''}</td><td class="small">${x.truth}</td><td>${decisionBadge(x.decision, x.decision_label)}</td><td><span class="badge ${(OUTCOME[x.outcome] || ['b-slate'])[0]}">${(OUTCOME[x.outcome] || [0, x.outcome])[1]}</span></td><td class="small">${x.similarity ?? '—'}</td></tr>`)}</tbody></table></div>` : empty({ icon: 'flask', title: 'No samples yet', text: 'Captures you record appear here.' }));
  }

  async function toggleCamera() {
    const btn = $('#cam-toggle', root);
    if (cam?.running) { cam.stop(); $('#ph', root).style.display = ''; setHTML(btn, h`${icon('camera')} Start camera`); $('#capture', root).disabled = true; return; }
    try { await cam.start(); $('#ph', root).style.display = 'none'; setHTML(btn, h`${icon('stop')} Stop camera`); $('#capture', root).disabled = !svc.available; }
    catch (e) { toast(describeCameraError(e), 'error', 7000); }
  }
  async function capture(e) {
    const btn = e.currentTarget; // read before any await: currentTarget is null afterwards
    const truth = $('#truth', root).value, cond = $('#cond', root).value.trim();
    const blob = await cam.capture(640, 0.9); if (!blob) return toast('The camera has no image yet.', 'warn');
    try {
      const r = await withBusy(btn, () => api.frame(`/api/evaluation/sample?truth=${encodeURIComponent(truth)}&condition=${encodeURIComponent(cond)}`, blob), 'Evaluating…');
      const o = OUTCOME[r.outcome] || ['b-slate', r.outcome];
      setHTML($('#last', root), h`<div class="callout ${o[0] === 'b-teal' ? 'ok' : o[0] === 'b-red' ? 'error' : 'warn'}">${icon(o[0] === 'b-teal' ? 'checkcircle' : 'alert')}<div><b>${o[1]}</b> · ${r.decision_label} · score ${r.similarity ?? '—'} · ${r.processing_ms} ms<div class="small">${r.reason}</div></div></div>`);
      load();
    } catch (ex) { setHTML($('#last', root), callout('warn', ex.message)); }
  }

  cam = new Camera($('#video', root));
  $('#cam-toggle', root).addEventListener('click', toggleCamera);
  $('#capture', root).addEventListener('click', capture);
  $('#reset', root)?.addEventListener('click', async () => {
    if (!(await confirmDialog({ title: 'Delete all evaluation samples?', message: 'Metrics return to "Not evaluated yet". This cannot be undone.', confirmText: 'Delete samples', danger: true }))) return;
    try { const r = await api.del('/api/evaluation/samples'); toast(`${r.deleted} sample(s) deleted.`); load(); } catch (e) { toast(e.message, 'error'); }
  });
  await load();
  return () => cam?.stop();
}
