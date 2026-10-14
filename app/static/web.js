/* NexusAC web transport.
   panel.js is the in-game panel, unchanged. In game it talks to NexusAC with
   fetch('https://NexusAC/<name>') and gets answers as window messages. This
   file catches exactly those calls, sends them to the website (which hands
   them to the game server), and turns the answers back into the same messages.
   Every other fetch passes straight through. */
(function () {
  'use strict';
  const SID = (document.querySelector('meta[name="nx-server"]') || {}).content;
  const PREFIX = 'https://NexusAC/';
  const realFetch = window.fetch.bind(window);
  window.GetParentResourceName = function () { return 'NexusAC'; };

  let info = null;
  let offline = false;

  function emit(msg) { window.postMessage(msg, window.location.origin); }

  function banner(text) {
    let el = document.getElementById('nx-web-banner');
    if (!text) { if (el) el.remove(); return; }
    if (!el) {
      el = document.createElement('div');
      el.id = 'nx-web-banner';
      document.body.appendChild(el);
    }
    el.textContent = text;
  }

  async function api(body) {
    let res;
    try {
      res = await realFetch('/api/s/' + encodeURIComponent(SID) + '/q', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-NX': '1' },
        body: JSON.stringify(body),
      });
    } catch (e) {
      return { ok: false, offline: true, msg: 'Cannot reach the website.' };
    }
    if (res.status === 401) { window.location.href = '/'; return { ok: false }; }
    let data;
    try { data = await res.json(); } catch (e) { data = { ok: false, msg: 'Bad answer from the website.' }; }
    if (data.offline) {
      offline = true;
      banner('The game server is not connected to the website. Retrying...');
    } else if (offline) {
      offline = false;
      banner(null);
    }
    return data;
  }

  async function open() {
    const r = await api({ kind: 'open' });
    if (r.ok && r.data) {
      info = r.data;
      emit({ type: 'open', data: info });
    } else {
      banner(r.msg || 'The game server is not connected to the website. Retrying...');
      setTimeout(open, 5000);
    }
  }

  async function handle(name, body) {
    if (name === 'ready') { open(); return; }
    if (name === 'section') {
      const r = await api({ kind: 'section', section: body.section, arg: body.arg });
      emit({ type: 'section', section: body.section, data: r.ok ? r.data : undefined,
        denied: !!r.denied, error: !r.ok && !r.denied && !r.offline, request: body.request });
      return;
    }
    if (name === 'exec') {
      const r = await api({ kind: 'exec', cmd: body });
      emit({ type: 'toast', data: { ok: !!r.ok, msg: r.msg || (r.ok ? 'Done.' : 'Refused.') } });
      return;
    }
    // Esc / the close button: there is nothing to close on the web, so the
    // panel simply opens again.
    if (name === 'close' && info) { setTimeout(function () { emit({ type: 'open', data: info }); }, 0); }
    // ready/opened/nxbeat/devtools are in-game only.
  }

  window.fetch = function (url, opts) {
    if (typeof url === 'string' && url.indexOf(PREFIX) === 0) {
      let body = {};
      try { body = JSON.parse((opts && opts.body) || '{}'); } catch (e) { /* empty */ }
      handle(url.slice(PREFIX.length), body);
      return Promise.resolve(new Response('{}', { headers: { 'Content-Type': 'application/json' } }));
    }
    return realFetch(url, opts);
  };

  // Back to the server list / sign out, added to the panel's own sidebar.
  document.addEventListener('DOMContentLoaded', function () {
    const tools = document.querySelector('.side-tools');
    if (!tools) return;
    const home = document.createElement('a');
    home.className = 'icon-btn nx-web-home';
    home.href = '/';
    home.title = 'Servers and accounts';
    home.textContent = '⌂';
    tools.appendChild(home);
  });
})();
