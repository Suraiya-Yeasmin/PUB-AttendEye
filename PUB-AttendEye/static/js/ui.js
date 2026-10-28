import { h, raw, esc, setHTML, $, $$ } from './util.js';
import { icon } from './icons.js';

// ---------- toasts ----------
export function toast(message, kind = 'ok', ms = 4500) {
  const el = document.createElement('div');
  el.className = `toast ${kind === 'ok' ? '' : kind}`;
  setHTML(el, h`${icon(kind === 'error' ? 'alert' : kind === 'warn' ? 'alert' : 'checkcircle')}<div>${message}</div>`);
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), ms);
}

// ---------- modal ----------
let stack = [];
export function openModal({ title, body, footer = '', wide = false, onMount, onClose }) {
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  const id = 'm' + Math.random().toString(36).slice(2, 7);
  setHTML(overlay, h`<div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-labelledby="${id}">
    <div class="modal-head"><h2 id="${id}">${title}</h2><button class="icon-btn" data-close aria-label="Close">${icon('x')}</button></div>
    <div class="modal-body">${body}</div>${footer ? h`<div class="modal-foot">${footer}</div>` : ''}</div>`);
  const prevFocus = document.activeElement;
  const close = (result) => { overlay.remove(); stack = stack.filter((s) => s !== api); document.removeEventListener('keydown', onKey); prevFocus?.focus?.(); onClose?.(result); };
  const onKey = (e) => { if (e.key === 'Escape' && stack[stack.length - 1] === api) close(); };
  overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
  overlay.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) close(); });
  document.addEventListener('keydown', onKey);
  $('#modal-root').appendChild(overlay);
  const api = { el: overlay, close, $: (s) => $(s, overlay), $$: (s) => $$(s, overlay) };
  stack.push(api);
  (overlay.querySelector('[autofocus],input,select,textarea,button.primary') || overlay.querySelector('.modal'))?.focus();
  onMount?.(api);
  return api;
}

export function confirmDialog({ title, message, confirmText = 'Confirm', danger = false, extra = '' }) {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal({
      title, body: h`<p>${message}</p>${extra}`,
      footer: h`<button class="btn" data-close>Cancel</button><button class="btn ${danger ? 'danger' : 'primary'}" data-ok>${confirmText}</button>`,
      onMount: (m) => m.$('[data-ok]').addEventListener('click', () => { done = true; m.close(true); }),
      onClose: () => resolve(done),
    });
  });
}

// Form modal: onSubmit(values, api) must resolve on success (modal closes) or throw ApiError with .fields.
export function formModal({ title, fields, submitText = 'Save', values = {}, onSubmit, wide = false, intro = '' }) {
  const body = h`<form novalidate class="form-grid" autocomplete="off">${intro ? h`<div class="full">${intro}</div>` : ''}${fields.map((f) => fieldHtml(f, values[f.name]))}</form><div class="err" data-form-err role="alert"></div>`;
  return openModal({
    title, body, wide,
    footer: h`<button class="btn" data-close>Cancel</button><button class="btn primary" data-submit>${submitText}</button>`,
    onMount: (m) => {
      const form = m.$('form'); const btn = m.$('[data-submit]');
      const run = async (e) => {
        e?.preventDefault();
        const vals = {}; let bad = false;
        for (const f of fields) {
          const inp = form.elements[f.name]; let v = f.type === 'checkbox' ? inp.checked : inp.value.trim();
          const errEl = form.querySelector(`[data-err="${f.name}"]`); errEl.textContent = ''; inp.classList.remove('invalid');
          if (f.required && !v) { errEl.textContent = `${f.label} is required.`; inp.classList.add('invalid'); bad = true; }
          else if (f.type === 'number' && v !== '') v = Number(v);
          if (f.pattern && v && !f.pattern.test(v)) { errEl.textContent = f.patternMsg || `${f.label} is not valid.`; inp.classList.add('invalid'); bad = true; }
          vals[f.name] = v;
        }
        if (bad) { form.querySelector('.invalid')?.focus(); return; }
        btn.disabled = true; const label = btn.innerHTML; setHTML(btn, h`<span class="spinner"></span> Saving…`);
        try { await onSubmit(vals, m); m.close(true); }
        catch (err) {
          btn.disabled = false; btn.innerHTML = label;
          let shown = false;
          Object.entries(err.fields || {}).forEach(([k, msg]) => { const e = form.querySelector(`[data-err="${k}"]`); if (e) { e.textContent = msg; form.elements[k]?.classList.add('invalid'); shown = true; } });
          if (!shown || !Object.keys(err.fields || {}).length) m.$('[data-form-err]').textContent = err.message || 'Could not save.';
        }
      };
      form.addEventListener('submit', run); btn.addEventListener('click', run);
    },
  });
}
export function fieldHtml(f, value) {
  const v = value ?? f.default ?? '';
  const cls = f.full ? 'field full' : 'field';
  const id = 'f_' + f.name;
  let control;
  if (f.type === 'select') control = h`<select class="select" id="${id}" name="${f.name}">${f.options.map((o) => h`<option value="${o.value}" ${String(o.value) === String(v) ? raw('selected') : ''}>${o.label}</option>`)}</select>`;
  else if (f.type === 'checkbox') return h`<div class="${cls}"><label class="check"><input type="checkbox" id="${id}" name="${f.name}" ${v ? raw('checked') : ''}><span>${f.label}${f.hint ? h`<br><span class="hint">${f.hint}</span>` : ''}</span></label><div class="err" data-err="${f.name}"></div></div>`;
  else control = h`<input class="input" id="${id}" name="${f.name}" type="${f.type || 'text'}" value="${v}" ${f.maxlength ? raw(`maxlength="${f.maxlength}"`) : ''} ${f.min != null ? raw(`min="${f.min}"`) : ''} ${f.max != null ? raw(`max="${f.max}"`) : ''} ${f.step ? raw(`step="${f.step}"`) : ''} ${f.placeholder ? raw(`placeholder="${esc(f.placeholder)}"`) : ''} ${f.readonly ? raw('readonly') : ''} ${f.autocomplete ? raw(`autocomplete="${f.autocomplete}"`) : ''}>`;
  return h`<div class="${cls}"><label for="${id}">${f.label}${f.required ? ' *' : ''}</label>${control}${f.hint ? h`<div class="hint">${f.hint}</div>` : ''}<div class="err" data-err="${f.name}"></div></div>`;
}

// ---------- dropdown menu ----------
export function menu(items) {
  return h`<div class="menu"><button class="icon-btn" data-menu aria-haspopup="true" aria-label="Actions">${icon('more')}</button><div class="menu-list" role="menu">${items.map((i) => (i === '-' ? h`<hr>` : h`<button role="menuitem" data-action="${i.action}" data-id="${i.id ?? ''}" class="${i.danger ? 'danger' : ''}">${icon(i.icon || 'arrow', 'sm')} ${i.label}</button>`))}</div></div>`;
}
document.addEventListener('click', (e) => {
  const trigger = e.target.closest('[data-menu]');
  $$('.menu.open').forEach((m) => { if (!trigger || m !== trigger.parentElement) m.classList.remove('open'); });
  if (trigger) trigger.parentElement.classList.toggle('open');
});

// ---------- badges / states ----------
const SESSION = { scheduled: ['b-blue', 'Scheduled'], active: ['b-teal', 'Active'], completed: ['b-slate', 'Completed'], cancelled: ['b-red', 'Cancelled'] };
export const sessionBadge = (s) => h`<span class="badge ${(SESSION[s] || ['b-slate'])[0]}">${(SESSION[s] || [0, s])[1]}</span>`;
const DECISION = { accepted: 'b-teal', needs_review: 'b-amber', unknown: 'b-red', poor_quality: 'b-slate', duplicate: 'b-blue', session_inactive: 'b-slate', error: 'b-red', pending: 'b-indigo' };
export const decisionBadge = (d, label) => h`<span class="badge ${DECISION[d] || 'b-slate'}">${label || d}</span>`;
const ATT = { present: 'b-teal', late: 'b-amber', excused: 'b-blue', absent: 'b-red' };
export const attBadge = (s) => h`<span class="badge ${ATT[s] || 'b-slate'}">${s[0].toUpperCase() + s.slice(1)}</span>`;
export const methodLabel = (m) => ({ face: 'Face recognition', face_review: 'Face + teacher review', manual: 'Manual (teacher)' }[m] || m || '—');
export const reviewLabel = (r) => ({ not_required: 'Not required', teacher_confirmed: 'Teacher confirmed' }[r] || r);
export const consentBadge = (s) => {
  if (s.face_enrolled) return h`<span class="badge b-teal">Face enrolled</span>`;
  if (s.biometric_consent === 'declined') return h`<span class="badge b-slate">Declined biometrics</span>`;
  if (s.biometric_consent === 'withdrawn') return h`<span class="badge b-amber">Consent withdrawn</span>`;
  return h`<span class="badge b-amber">Not enrolled</span>`;
};
export const empty = ({ icon: ic = 'inbox', title, text = '', action = '' }) => h`<div class="empty"><div class="ico">${icon(ic, 'lg')}</div><h3>${title}</h3><p>${text}</p>${action}</div>`;
export const callout = (kind, content, ic) => h`<div class="callout ${kind}">${icon(ic || (kind === 'ok' ? 'checkcircle' : kind === 'info' ? 'info' : 'alert'))}<div>${content}</div></div>`;
export const loading = () => h`<div class="empty"><span class="spinner"></span><p style="margin-top:10px">Loading…</p></div>`;
export const errorBox = (e) => callout('error', e.message || 'Something went wrong.');

export function statCard({ label, value, sub = '', tone = 'slate', ic, href }) {
  const inner = h`<div class="top"><span>${label}</span><span class="ico tone-${tone}">${icon(ic)}</span></div><div class="num">${value}</div><div class="sub">${sub}</div>`;
  return href ? h`<a class="stat" href="${href}">${inner}</a>` : h`<div class="stat">${inner}</div>`;
}
export function button(btn, busy, text) { btn.disabled = !!busy; if (busy) { btn.dataset.l = btn.innerHTML; setHTML(btn, h`<span class="spinner"></span> ${text || 'Working…'}`); } else if (btn.dataset.l) { btn.innerHTML = btn.dataset.l; } }
export async function withBusy(btn, fn, text) { button(btn, true, text); try { return await fn(); } finally { button(btn, false); } }
