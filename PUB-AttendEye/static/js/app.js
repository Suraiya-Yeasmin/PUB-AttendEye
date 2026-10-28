import { api, setUnauthorizedHandler, ApiError } from './api.js';
import { h, raw, setHTML, $, $$, initials, fmtDate } from './util.js';
import { icon, logoMark } from './icons.js';
import { toast, loading, errorBox, confirmDialog, withBusy } from './ui.js';

const ROUTES = {
  dashboard: { title: 'Dashboard', icon: 'dashboard', load: () => import('./pages/dashboard.js') },
  live: { title: 'Live Attendance', icon: 'camera', load: () => import('./pages/live.js') },
  students: { title: 'Students', icon: 'users', load: () => import('./pages/students.js') },
  enroll: { title: 'Face Enrollment', icon: 'faceid', load: () => import('./pages/enroll.js') },
  classes: { title: 'Classes & Sessions', icon: 'book', load: () => import('./pages/classes.js') },
  review: { title: 'Review Queue', icon: 'inbox', load: () => import('./pages/review.js'), badge: true },
  history: { title: 'Attendance History', icon: 'history', load: () => import('./pages/history.js') },
  reports: { title: 'Reports & Analytics', icon: 'chart', load: () => import('./pages/reports.js') },
  evaluation: { title: 'System Evaluation', icon: 'gauge', load: () => import('./pages/evaluation.js') },
  settings: { title: 'Settings', icon: 'settings', load: () => import('./pages/settings.js') },
};
const app = $('#app');
const state = { teacher: null, cleanup: null, health: null, pending: 0, token: 0 };

setUnauthorizedHandler(() => { if (state.teacher) { state.teacher = null; toast('Your session has ended. Please sign in again.', 'warn'); showLogin(); } });

// ------------------------------------------------------------------ login
const loginArt = () => h`    <section class="login-art" aria-label="PUB AttendEye classroom attendance">
      <div class="row login-brand" style="gap:12px;position:relative;z-index:1"><div class="brand-mark" style="width:42px;height:42px">${logoMark()}</div><b style="font-size:19px">PUB AttendEye</b></div>
      <div class="login-illustration-wrap"><img class="login-illustration" src="/static/images/teacher-attendance.svg" alt="Illustration of a teacher taking classroom attendance using a tablet"></div>
    </section>`;

const getOptions = async () => { try { return await api.get('/api/auth/options'); } catch { return {}; } };

// Shared "Create new account" / "Try the demo" block shown under the sign-in and setup forms.
function altActions(opts, { signup = true } = {}) {
  if (!(signup && opts.signup_enabled) && !opts.demo_enabled) return '';
  return h`<div class="login-alt"><div class="or"><span>or</span></div>
    ${signup && opts.signup_enabled ? h`<button type="button" class="btn block" id="go-register" style="min-height:42px">${icon('userplus')} Create new account</button>` : ''}
    ${opts.demo_enabled ? h`<button type="button" class="btn block" id="go-demo" style="min-height:42px">${icon('play')} Try the demo account</button>
    <p class="hint">The demo uses fictional sample students. It never mixes with real records.</p>` : ''}</div>`;
}
function wireAlt(opts) {
  $('#go-register')?.addEventListener('click', () => showRegister(opts));
  $('#go-demo')?.addEventListener('click', async (e) => {
    const err = $('#login-err') || $('#setup-err') || $('#reg-err');
    try { await withBusy(e.currentTarget, async () => { const r = await api.post('/api/auth/demo'); state.teacher = r.teacher; }, 'Opening demo…'); location.hash = '#/dashboard'; startShell(); }
    catch (ex) { if (err) { setHTML(err, h`${icon('alert')}<div>${ex.message}</div>`); err.style.display = 'flex'; } }
  });
}

async function showLogin() {
  cleanup();
  const opts = await getOptions();
  setHTML(app, h`<div class="login">
    ${loginArt()}
    <section class="login-form"><form class="login-card" novalidate id="login-form">
      <h1>Teacher sign in</h1><p class="muted" style="margin-bottom:22px">Use your PUB AttendEye teacher account.</p>
      <div class="field" style="margin-bottom:14px"><label for="u">Username or email</label><input class="input" id="u" name="username" autocomplete="username" autofocus><div class="err" data-err="u"></div></div>
      <div class="field" style="margin-bottom:6px"><label for="p">Password</label><div class="input-wrap"><input class="input" style="padding-left:12px;padding-right:40px" id="p" name="password" type="password" autocomplete="current-password"><button type="button" class="icon-btn pw-toggle" aria-label="Show password" id="pw-toggle">${icon('eye')}</button></div><div class="err" data-err="p"></div></div>
      <div class="callout error" id="login-err" role="alert" style="display:none;margin:12px 0"></div>
      <button class="btn primary block" id="login-btn" style="margin-top:14px;min-height:42px">Sign in</button>
      ${altActions(opts)}
      <p class="hint" style="margin-top:18px">Passwords are stored hashed on this computer.</p>
    </form></section></div>`);
  wireAlt(opts);
  const form = $('#login-form'), pw = $('#p');
  $('#pw-toggle').addEventListener('click', (e) => { const show = pw.type === 'password'; pw.type = show ? 'text' : 'password'; setHTML(e.currentTarget, icon(show ? 'eyeoff' : 'eye')); e.currentTarget.setAttribute('aria-label', show ? 'Hide password' : 'Show password'); });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const u = $('#u').value.trim(), p = pw.value; const err = $('#login-err'); err.style.display = 'none';
    $$('[data-err]', form).forEach((x) => (x.textContent = ''));
    let bad = false;
    if (!u) { $('[data-err=u]').textContent = 'Enter your username or email.'; bad = true; }
    if (!p) { $('[data-err=p]').textContent = 'Enter your password.'; bad = true; }
    if (bad) return;
    try {
      await withBusy($('#login-btn'), async () => { const r = await api.post('/api/auth/login', { username: u, password: p }); state.teacher = r.teacher; }, 'Signing in…');
      location.hash = '#/dashboard'; startShell();
    } catch (ex) { setHTML(err, h`${icon('alert')}<div>${ex.message}</div>`); err.style.display = 'flex'; pw.value = ''; pw.focus(); }
  });
}

// ------------------------------------------------------------------ create new account
function showRegister(opts) {
  cleanup();
  setHTML(app, h`<div class="login">
    ${loginArt()}
    <section class="login-form"><form class="login-card" novalidate id="reg-form">
      <h1>Create new account</h1><p class="muted" style="margin-bottom:22px">Make a teacher account for this computer. An administrator can change your role later.</p>
      <div class="field" style="margin-bottom:12px"><label for="r-name">Full name</label><input class="input" id="r-name" autocomplete="name" autofocus><div class="err" data-err="r-name"></div></div>
      <div class="field" style="margin-bottom:12px"><label for="r-email">Email</label><input class="input" id="r-email" type="email" autocomplete="email"><div class="err" data-err="r-email"></div></div>
      <div class="field" style="margin-bottom:12px"><label for="r-user">Username</label><input class="input" id="r-user" autocomplete="username"><div class="err" data-err="r-user"></div></div>
      <div class="field" style="margin-bottom:12px"><label for="r-pw">Password (at least 8 characters)</label><input class="input" id="r-pw" type="password" autocomplete="new-password"><div class="err" data-err="r-pw"></div></div>
      <div class="field" style="margin-bottom:6px"><label for="r-pw2">Repeat password</label><input class="input" id="r-pw2" type="password" autocomplete="new-password"><div class="err" data-err="r-pw2"></div></div>
      <div class="callout error" id="reg-err" role="alert" style="display:none;margin:12px 0"></div>
      <button class="btn primary block" id="reg-btn" style="margin-top:14px;min-height:42px">Create account</button>
      <button type="button" class="btn ghost block" id="reg-back" style="margin-top:8px">Back to sign in</button>
    </form></section></div>`);
  $('#reg-back').addEventListener('click', showLogin);
  const form = $('#reg-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const v = (id) => $('#' + id).value, err = $('#reg-err'); err.style.display = 'none';
    $$('[data-err]', form).forEach((x) => (x.textContent = ''));
    const name = v('r-name').trim(), email = v('r-email').trim(), user = v('r-user').trim(), pw = v('r-pw'), pw2 = v('r-pw2');
    const bad = {};
    if (name.length < 2) bad['r-name'] = 'Enter your full name.';
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) bad['r-email'] = 'Enter a valid email address.';
    if (!/^[A-Za-z0-9._-]{3,64}$/.test(user)) bad['r-user'] = 'Use 3+ letters, numbers, dots, dashes or underscores.';
    if (pw.length < 8) bad['r-pw'] = 'Use at least 8 characters.';
    if (pw !== pw2) bad['r-pw2'] = 'Passwords do not match.';
    for (const [k, m] of Object.entries(bad)) $(`[data-err=${k}]`).textContent = m;
    if (Object.keys(bad).length) return;
    try {
      await withBusy($('#reg-btn'), async () => { const r = await api.post('/api/auth/register', { full_name: name, email, username: user, password: pw }); state.teacher = r.teacher; }, 'Creating account…');
      location.hash = '#/dashboard'; startShell(); toast('Account created. You are signed in.');
    } catch (ex) { setHTML(err, h`${icon('alert')}<div>${ex.message}</div>`); err.style.display = 'flex'; }
  });
}

// ------------------------------------------------------------------ first-run setup
async function showSetup() {
  cleanup();
  const opts = await getOptions();
  setHTML(app, h`<div class="login">
    ${loginArt()}
    <section class="login-form"><form class="login-card" novalidate id="setup-form">
      <h1>Welcome to PUB AttendEye</h1><p class="muted" style="margin-bottom:22px">Create the administrator account for this computer. You only do this once.</p>
      <div class="field" style="margin-bottom:12px"><label for="s-name">Full name</label><input class="input" id="s-name" autocomplete="name" autofocus><div class="err" data-err="s-name"></div></div>
      <div class="field" style="margin-bottom:12px"><label for="s-email">Email</label><input class="input" id="s-email" type="email" autocomplete="email"><div class="err" data-err="s-email"></div></div>
      <div class="field" style="margin-bottom:12px"><label for="s-user">Username</label><input class="input" id="s-user" autocomplete="username"><div class="err" data-err="s-user"></div></div>
      <div class="field" style="margin-bottom:12px"><label for="s-pw">Password (at least 8 characters)</label><input class="input" id="s-pw" type="password" autocomplete="new-password"><div class="err" data-err="s-pw"></div></div>
      <div class="field" style="margin-bottom:6px"><label for="s-pw2">Repeat password</label><input class="input" id="s-pw2" type="password" autocomplete="new-password"><div class="err" data-err="s-pw2"></div></div>
      <div class="callout error" id="setup-err" role="alert" style="display:none;margin:12px 0"></div>
      <button class="btn primary block" id="setup-btn" style="margin-top:14px;min-height:42px">Create account and start</button>
      ${altActions(opts, { signup: false })}
      <p class="hint" style="margin-top:18px">Everything stays on this computer. Keep this password safe: there is no online reset.</p>
    </form></section></div>`);
  wireAlt(opts);
  const form = $('#setup-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const v = (id) => $('#' + id).value, err = $('#setup-err'); err.style.display = 'none';
    $$('[data-err]', form).forEach((x) => (x.textContent = ''));
    const name = v('s-name').trim(), email = v('s-email').trim(), user = v('s-user').trim(), pw = v('s-pw'), pw2 = v('s-pw2');
    const bad = {};
    if (name.length < 2) bad['s-name'] = 'Enter your full name.';
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) bad['s-email'] = 'Enter a valid email address.';
    if (!/^[A-Za-z0-9._-]{3,64}$/.test(user)) bad['s-user'] = 'Use 3+ letters, numbers, dots, dashes or underscores.';
    if (pw.length < 8) bad['s-pw'] = 'Use at least 8 characters.';
    if (pw !== pw2) bad['s-pw2'] = 'Passwords do not match.';
    for (const [k, m] of Object.entries(bad)) $(`[data-err=${k}]`).textContent = m;
    if (Object.keys(bad).length) return;
    try {
      await withBusy($('#setup-btn'), async () => { const r = await api.post('/api/setup', { full_name: name, email, username: user, password: pw }); state.teacher = r.teacher; }, 'Creating account…');
      location.hash = '#/dashboard'; startShell();
    } catch (ex) { setHTML(err, h`${icon('alert')}<div>${ex.message}</div>`); err.style.display = 'flex'; }
  });
}

// ------------------------------------------------------------------ shell
function startShell() {
  const t = state.teacher;
  setHTML(app, h`<div class="shell">
    <aside class="sidebar" id="sidebar" aria-label="Primary">
      <div class="brand"><div class="brand-mark">${logoMark()}</div><div><b>PUB AttendEye</b><span>Smart attendance</span></div></div>
      <nav class="nav">${Object.entries(ROUTES).map(([k, r]) => h`<a href="#/${k}" data-route="${k}">${icon(r.icon)}<span>${r.title}</span>${r.badge ? h`<span class="count" id="nav-badge" hidden></span>` : ''}</a>`)}</nav>
      <div class="sidebar-foot"><div class="avatar">${initials(t.full_name)}</div><div class="who"><b>${t.full_name}</b><span>${t.role}</span></div><button class="icon-btn" id="logout" title="Sign out" aria-label="Sign out">${icon('logout')}</button></div>
    </aside>
    <div class="main">
      <header class="topbar">
        <button class="icon-btn menu-btn" id="menu-btn" aria-label="Open navigation">${icon('menu')}</button>
        <div class="titles"><div class="crumbs" id="crumbs"></div><h1 id="page-title"></h1></div>
        ${t.username === 'demo' ? h`<span class="badge b-amber" title="Fictional sample data. Sign out and sign in with your own account for real records.">Demo account · sample data</span>` : ''}<span class="date">${fmtDate(new Date().toISOString())}</span>
        <span class="badge plain b-slate" id="health" title="Face-recognition service status"></span>
        <a class="icon-btn" href="#/review" id="bell" aria-label="Pending reviews" style="position:relative">${icon('bell')}<span class="count" id="bell-count" hidden style="position:absolute;top:2px;right:0;background:var(--amber-500);color:#3b2500;font-size:10px;font-weight:700;padding:0 5px;border-radius:99px"></span></a>
        <div class="menu" id="profile-menu"><button class="row" data-menu style="background:none;border:0;cursor:pointer;gap:9px" aria-haspopup="true"><div class="avatar" style="width:34px;height:34px;background:var(--navy-700)">${initials(t.full_name)}</div></button>
          <div class="menu-list"><div style="padding:8px 10px"><b>${t.full_name}</b><div class="small muted">${t.email}</div></div><hr><a href="#/settings">${icon('settings', 'sm')} Profile & settings</a><button data-logout>${icon('logout', 'sm')} Sign out</button></div></div>
      </header>
      <main class="content" id="view" tabindex="-1"></main>
    </div></div>`);
  const out = async () => { try { await api.post('/api/auth/logout'); } catch {} state.teacher = null; location.hash = ''; showLogin(); };
  $('#logout').addEventListener('click', out); $('[data-logout]').addEventListener('click', out);
  $('#menu-btn').addEventListener('click', () => $('#sidebar').classList.toggle('open'));
  $('#sidebar').addEventListener('click', (e) => { if (e.target.closest('a')) $('#sidebar').classList.remove('open'); });
  refreshHealth(); refreshPending();
  clearInterval(state.timer); state.timer = setInterval(() => { refreshHealth(); refreshPending(); }, 30000);
  route();
}
async function refreshHealth() {
  try { const r = await api.get('/api/health'); state.health = r; const el = $('#health'); if (!el) return;
    el.className = `badge ${r.cv_available ? 'b-teal' : 'b-red'}`; el.textContent = r.cv_available ? 'Recognition ready' : 'Recognition offline'; el.title = r.cv_available ? 'Face detection and recognition models are loaded.' : (r.cv_error || 'Models not loaded'); } catch {}
}
async function refreshPending() {
  try { const r = await api.get('/api/review?status=pending&limit=1'); state.pending = r.pending_total;
    for (const [id] of [['nav-badge'], ['bell-count']]) { const el = document.getElementById(id); if (el) { el.hidden = !r.pending_total; el.textContent = r.pending_total; } } } catch {}
}
window.__refreshPending = refreshPending;

function cleanup() { try { state.cleanup?.(); } catch {} state.cleanup = null; }

async function route() {
  if (!state.teacher) return;
  const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const key = ROUTES[path] ? path : 'dashboard';
  if (!ROUTES[path]) { history.replaceState(null, '', '#/dashboard'); }
  cleanup();
  // A fresh container per navigation: listeners that a previous page attached to the view element are dropped with it.
  const old = $('#view'), view = old.cloneNode(false); old.replaceWith(view);
  const r = ROUTES[key], token = ++state.token;
  $$('.nav a').forEach((a) => a.classList.toggle('active', a.dataset.route === key));
  $('#page-title').textContent = r.title; document.title = `${r.title} · PUB AttendEye`;
  setHTML($('#crumbs'), h`<a href="#/dashboard">Home</a> / ${r.title}`);
  setHTML(view, loading());
  try {
    const mod = await r.load();
    if (token !== state.token) return;
    view.innerHTML = '';
    const ctx = { teacher: state.teacher, params: new URLSearchParams(query), refreshPending, health: () => state.health,
      crumbs: (extra) => setHTML($('#crumbs'), h`<a href="#/dashboard">Home</a> / <a href="#/${key}">${r.title}</a> / ${extra}`),
      navigate: (hash) => { location.hash = hash; } };
    const c = await mod.default(view, ctx);
    if (token === state.token) state.cleanup = typeof c === 'function' ? c : null; else if (typeof c === 'function') c();
    view.focus({ preventScroll: true });
  } catch (e) {
    if (token === state.token) setHTML(view, errorBox(e instanceof ApiError ? e : new Error('This page failed to load: ' + e.message)));
    console.error(e);
  }
}
window.addEventListener('hashchange', route);

// ------------------------------------------------------------------ boot
(async function boot() {
  setHTML(app, loading());
  try { const r = await api.get('/api/auth/me'); state.teacher = r.teacher; startShell(); }
  catch {
    let needs = false;
    try { needs = (await api.get('/api/setup/status')).needs_setup; } catch {}
    needs ? showSetup() : showLogin();
  }
})();
