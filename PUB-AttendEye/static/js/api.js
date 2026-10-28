// Thin fetch wrapper. All state-changing calls carry the CSRF header the server requires.
const HEADERS = { 'X-Requested-With': 'AttendEye' };
export class ApiError extends Error {
  constructor(status, message, fields = {}) { super(message); this.status = status; this.fields = fields; }
}
let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

async function request(method, url, { json, body, headers } = {}) {
  const opts = { method, headers: { ...HEADERS, ...(headers || {}) }, credentials: 'same-origin' };
  if (json !== undefined) { opts.body = JSON.stringify(json); opts.headers['Content-Type'] = 'application/json'; }
  else if (body !== undefined) opts.body = body;
  let res;
  try { res = await fetch(url, opts); }
  catch { throw new ApiError(0, 'Cannot reach the PUB AttendEye server. Is it still running?'); }
  if (res.status === 204) return null;
  const ctype = res.headers.get('content-type') || '';
  const data = ctype.includes('application/json') ? await res.json() : res;
  if (!res.ok) {
    const d = data && data.detail;
    const msg = typeof d === 'string' ? d : (d && d.message) || res.statusText || 'Request failed';
    if (res.status === 401 && !url.includes('/auth/login')) onUnauthorized();
    throw new ApiError(res.status, msg, (d && d.fields) || {});
  }
  return data;
}
export const api = {
  get: (u) => request('GET', u),
  post: (u, json) => request('POST', u, { json: json ?? {} }),
  put: (u, json) => request('PUT', u, { json }),
  del: (u) => request('DELETE', u),
  frame: (u, blob) => request('POST', u, { body: blob, headers: { 'Content-Type': 'image/jpeg' } }),
};
export async function download(url, fallbackName) {
  const res = await fetch(url, { credentials: 'same-origin', headers: HEADERS });
  if (!res.ok) { let m = 'Export failed'; try { const j = await res.json(); m = j.detail?.message || j.detail || m; } catch {} throw new ApiError(res.status, m); }
  const rows = Number(res.headers.get('X-Row-Count') || '0');
  const cd = res.headers.get('Content-Disposition') || '';
  const name = (cd.match(/filename="([^"]+)"/) || [])[1] || fallbackName;
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  return { rows, name };
}
