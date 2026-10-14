'use strict';
const ORIGIN = location.origin;

function connectLines(key) {
  return 'set nexus_web_url "' + ORIGIN + '"\nset nexus_web_token "' + key + '"';
}

function showKey(name, key) {
  document.getElementById('key').innerHTML = '<div class="keybox"><b>Key for ' + esc(name) + ' (shown once).</b> Put these two lines in server.cfg above <code style="display:inline;padding:0 4px">ensure NexusAC</code>, then restart NexusAC:' +
    '<code>' + esc(connectLines(key)) + '</code></div>';
}

async function load() {
  const r = await call('GET', '/api/me');
  if (!r.ok) return;
  const owner = r.user.role === 'owner';
  document.getElementById('who').textContent = r.user.username + ' (' + r.user.role + ')';

  const servers = r.servers.map((s) => '<div class="item"><i class="dot' + (s.online ? ' on' : '') + '"></i><div class="grow"><b>' + esc(s.name) + '</b>' +
    '<small class="muted">' + (s.online ? 'Connected' + (s.info && s.info.players != null ? ' &middot; ' + esc(s.info.players) + ' online' : '') + (s.info && s.info.version ? ' &middot; v' + esc(s.info.version) : '')
      : 'Not connected' + (owner && s.keyPrefix ? ' &middot; key ' + esc(s.keyPrefix) + '...' : '')) + '</small></div>' +
    '<a class="btn primary small" href="/s/' + encodeURIComponent(s.id) + '">Open panel</a>' +
    (owner ? '<button class="btn small" data-rotate="' + esc(s.id) + '" data-name="' + esc(s.name) + '">New key</button><button class="btn small danger" data-del-server="' + esc(s.id) + '" data-name="' + esc(s.name) + '">Remove</button>' : '') +
    '</div>').join('');
  document.getElementById('servers').innerHTML = servers || '<span class="muted">' + (owner ? 'No servers yet. Add one below.' : 'No servers yet. Ask the owner to add one.') + '</span>';

  document.getElementById('owner-servers').hidden = !owner;
  document.getElementById('owner-users').hidden = !owner;
  if (owner) {
    document.getElementById('role-pick').innerHTML = r.roles.map((x) => '<option>' + esc(x) + '</option>').join('');
    document.getElementById('users').innerHTML = r.users.map((u) => '<div class="item"><div class="grow"><b>' + esc(u.username) + '</b><small class="muted">' + esc(u.role) + '</small></div>' +
      (u.username === r.user.username ? '<span class="dim">you</span>' : '<button class="btn small danger" data-del-user="' + esc(u.username) + '">Delete</button>') + '</div>').join('');
  }
  // One server and not the owner: go straight to the panel.
  if (!owner && r.servers.length === 1 && !sessionStorage.getItem('nx-stay')) {
    sessionStorage.setItem('nx-stay', '1');
    location.href = '/s/' + encodeURIComponent(r.servers[0].id);
  }
}

document.addEventListener('click', async (ev) => {
  const t = ev.target.closest('button');
  if (!t) return;
  if (t.dataset.rotate) {
    if (!confirm('Make a new key for ' + t.dataset.name + '? The old key stops working at once.')) return;
    const r = await call('POST', '/api/servers/' + encodeURIComponent(t.dataset.rotate) + '/rotate');
    if (r.ok) showKey(t.dataset.name, r.key);
  } else if (t.dataset.delServer) {
    if (!confirm('Remove ' + t.dataset.name + ' from the website?')) return;
    await call('DELETE', '/api/servers/' + encodeURIComponent(t.dataset.delServer));
    load();
  } else if (t.dataset.delUser) {
    if (!confirm('Delete the account ' + t.dataset.delUser + '?')) return;
    await call('DELETE', '/api/users/' + encodeURIComponent(t.dataset.delUser));
    load();
  } else if (t.id === 'logout') {
    await call('POST', '/api/logout');
    location.href = '/';
  }
});

formTo('add-server', '/api/servers', (r, f) => { showKey(f.elements['name'].value, r.key); f.reset(); load(); });
formTo('add-user', '/api/users', (r, f) => { f.reset(); load(); });
formTo('pw', '/api/password', (r, f) => { f.reset(); document.getElementById('pw-err').textContent = 'Password changed.'; }, 'pw-err');
load();
setInterval(load, 15000);
