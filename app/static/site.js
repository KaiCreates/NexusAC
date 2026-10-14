'use strict';
/* Shared by the sign-in, setup and server pages. */
async function call(method, url, body) {
  const res = await fetch(url, {
    method, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-NX': '1' },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (e) { data = { ok: false, msg: 'Unexpected answer (' + res.status + ').' }; }
  if (res.status === 401 && url !== '/api/login') { location.href = '/'; }
  return data;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function formTo(id, url, done, errId) {
  const f = document.getElementById(id);
  f.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const body = Object.fromEntries(new FormData(f).entries());
    const btn = f.querySelector('button[type=submit]');
    btn.disabled = true;
    const r = await call('POST', url, body);
    btn.disabled = false;
    const err = document.getElementById(errId || 'err');
    if (err) err.textContent = r.ok ? '' : (r.msg || 'Failed.');
    if (r.ok) done(r, f);
  });
}
