// Safe HTML templating: every interpolated value is escaped unless wrapped in raw() or produced by h``.
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Raw(s);
const MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => MAP[c]);
const part = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join('') : v == null || v === false ? '' : esc(v));
export function h(strings, ...vals) {
  let out = '';
  strings.forEach((s, i) => { out += s + (i < vals.length ? part(vals[i]) : ''); });
  return new Raw(out);
}
export const setHTML = (el, tpl) => { el.innerHTML = tpl instanceof Raw ? tpl.s : Array.isArray(tpl) ? part(tpl) : esc(tpl); return el; };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const qs = (obj) => { const p = new URLSearchParams(); Object.entries(obj).forEach(([k, v]) => { if (v !== '' && v != null) p.set(k, v); }); const s = p.toString(); return s ? '?' + s : ''; };

const dateFmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
const timeFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
const timeSecFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
export const fmtDate = (iso) => (iso ? dateFmt.format(new Date(iso.length === 10 ? iso + 'T00:00:00' : iso)) : '—');
export const fmtTime = (iso) => (iso ? timeFmt.format(new Date(iso)) : '—');
export const fmtTimeSec = (iso) => (iso ? timeSecFmt.format(new Date(iso)) : '—');
export const fmtDateTime = (iso) => (iso ? `${fmtDate(iso)}, ${fmtTime(iso)}` : '—');
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
export const initials = (n) => (n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
export const pct = (v) => (v == null ? '—' : `${v}%`);
export const addMinutes = (hhmm, min) => { const [H, M] = hhmm.split(':').map(Number); const t = (H * 60 + M + min) % 1440; return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`; };
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
