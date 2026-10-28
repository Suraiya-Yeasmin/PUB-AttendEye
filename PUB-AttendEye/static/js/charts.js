import { h, raw, esc } from './util.js';

const C = { teal: '#12a58f', amber: '#f59e0b', red: '#dc2626', blue: '#2563eb', slate: '#94a3b8', indigo: '#5b5fe0', navy: '#16355f' };
export const COLORS = C;

export function donut(parts, { size = 170, center = '', sub = '' } = {}) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  const r = 62, cx = 85, cy = 85, circ = 2 * Math.PI * r;
  let off = 0;
  const arcs = total ? parts.filter((p) => p.value > 0).map((p) => { const len = (p.value / total) * circ; const a = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${p.color}" stroke-width="22" stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="${-off}" transform="rotate(-90 ${cx} ${cy})"><title>${esc(p.label)}: ${p.value}</title></circle>`; off += len; return a; }).join('') : `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#e8edf4" stroke-width="22"/>`;
  return h`<div class="donut-wrap"><div class="chart" style="width:${size}px"><svg viewBox="0 0 170 170" role="img" aria-label="${parts.map((p) => `${p.label} ${p.value}`).join(', ')}">${raw(arcs)}<text x="85" y="86" text-anchor="middle" style="font-size:26px;font-weight:700;fill:#0f1b2d">${center}</text><text x="85" y="104" text-anchor="middle">${sub}</text></svg></div><ul>${parts.map((p) => h`<li><i style="background:${p.color}"></i>${p.label}<b>${p.value}</b></li>`)}</ul></div>`;
}

// Vertical bars, values 0..max (percent by default). items: [{label, value, color?}]
export function bars(items, { max = 100, height = 190, unit = '%', color = C.teal } = {}) {
  const W = 560, padL = 34, padB = 40, padT = 12, H = height + padB + padT;
  const n = Math.max(items.length, 1), slot = (W - padL) / n, bw = Math.min(46, slot * 0.6);
  const grid = [0, 25, 50, 75, 100].map((g) => { const y = padT + height - (g / 100) * height; return `<line x1="${padL}" x2="${W}" y1="${y}" y2="${y}" stroke="#e8edf4"/><text x="${padL - 6}" y="${y + 4}" text-anchor="end">${Math.round((g / 100) * max)}</text>`; }).join('');
  const b = items.map((it, i) => {
    const x = padL + i * slot + (slot - bw) / 2;
    if (it.value == null) return `<text x="${x + bw / 2}" y="${padT + height - 6}" text-anchor="middle">n/a</text><text x="${x + bw / 2}" y="${padT + height + 16}" text-anchor="middle">${esc(shortLabel(it.label))}</text>`;
    const hh = Math.max((Math.min(it.value, max) / max) * height, 1), y = padT + height - hh;
    return `<rect x="${x}" y="${y}" width="${bw}" height="${hh}" rx="5" fill="${it.color || color}"><title>${esc(it.label)}: ${it.value}${unit}</title></rect><text x="${x + bw / 2}" y="${y - 5}" text-anchor="middle" style="fill:#3b4a60;font-weight:600">${it.value}${unit}</text><text x="${x + bw / 2}" y="${padT + height + 16}" text-anchor="middle">${esc(shortLabel(it.label))}</text>`;
  }).join('');
  return h`<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart">${raw(grid + b)}</svg></div>`;
}
const shortLabel = (s) => (String(s).length > 12 ? String(s).slice(0, 11) + '…' : s);

export function line(points, { height = 190, color = C.teal, max = 100 } = {}) {
  const W = 560, padL = 34, padB = 40, padT = 14, H = height + padB + padT;
  const valid = points.filter((p) => p.value != null);
  if (!valid.length) return h`<div class="empty small">No percentage data yet.</div>`;
  const step = points.length > 1 ? (W - padL - 20) / (points.length - 1) : 0;
  const xy = points.map((p, i) => [padL + 10 + i * step, p.value == null ? null : padT + height - (p.value / max) * height]);
  const grid = [0, 25, 50, 75, 100].map((g) => { const y = padT + height - (g / 100) * height; return `<line x1="${padL}" x2="${W}" y1="${y}" y2="${y}" stroke="#e8edf4"/><text x="${padL - 6}" y="${y + 4}" text-anchor="end">${g}</text>`; }).join('');
  const path = xy.filter((p) => p[1] != null).map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');
  const dots = xy.map((p, i) => (p[1] == null ? '' : `<circle cx="${p[0]}" cy="${p[1]}" r="4.5" fill="#fff" stroke="${color}" stroke-width="2.5"><title>${esc(points[i].label)}: ${points[i].value}%</title></circle>`)).join('');
  const labels = xy.map((p, i) => (points.length > 8 && i % 2 ? '' : `<text x="${p[0]}" y="${padT + height + 16}" text-anchor="middle">${esc(shortLabel(points[i].label))}</text>`)).join('');
  return h`<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Attendance trend">${raw(grid + `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/>` + dots + labels)}</svg></div>`;
}

// Horizontal stacked bar for evaluation outcomes
export function stacked(parts) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  if (!total) return h`<div class="empty small">No samples.</div>`;
  return h`<div class="chart"><div style="display:flex;height:26px;border-radius:8px;overflow:hidden;border:1px solid var(--border)">${parts.filter((p) => p.value).map((p) => h`<div title="${p.label}: ${p.value}" style="flex:${p.value};background:${p.color}"></div>`)}</div>
  <div class="legend" style="margin-top:10px">${parts.map((p) => h`<span><i style="background:${p.color}"></i>${p.label} <b>${p.value}</b></span>`)}</div></div>`;
}
