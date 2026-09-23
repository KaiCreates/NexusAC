/* The raw event log.

   Reads /api/control/events. Everything meaningful about a query lives in the
   URL, so a link to a filtered view is shareable and the back button works --
   which matters more than it sounds when two people are looking at the same
   incident.

   The table does not auto-refresh. An event log that repaints under you while
   you are reading row 40 of page 3 is actively hostile; there is a Search
   button, and it is the only thing that moves the page. */

const TYPE_COLOUR = {
  playerConnecting: '#c8703c',
  playerDropped:    '#c8615a',
  playerKilled:     '#b8377f',
  playerDamaged:    '#a83a86',
  playerDamage:     '#a83a86',
  weaponDamage:     '#a83a86',
  weaponFired:      '#8d2b3f',
  explosionEvent:   '#6f7248',
  entityCreated:    '#b08a5e',
  entityRemoved:    '#7a4bb5',
  vehicleSpawned:   '#3d9a94',
  detection:        '#c0392b',
};

/* Anything the resource starts emitting later still gets a stable colour
   instead of falling back to grey for everything. */
function colourFor(type) {
  if (TYPE_COLOUR[type]) return TYPE_COLOUR[type];
  let hash = 0;
  for (let i = 0; i < type.length; i++) hash = (hash * 31 + type.charCodeAt(i)) >>> 0;
  return `hsl(${hash % 360} 42% 42%)`;
}

const COLUMNS = ['time', 'type', 'data', 'sender', 'target'];

const state = {
  q: '',
  type: 'all',
  window: 'all',
  page: 1,
  size: 25,
  total: 0,
  capped: false,
  rows: [],
  hidden: new Set(),
};

const el = (id) => document.getElementById(id);

/* --------------------------------------------------------------------- */
async function loadWorkspace() {
  const result = await api('/workspace');
  if (!result.ok) return;
  const me = result.data.user || {};
  const current = (result.data.workspaces || []).find((w) => w.id === me.workspace);
  const name = (current && current.name) || 'Workspace';
  el('ws-name').firstChild.textContent = name;
  el('ws-initial').textContent = name.charAt(0).toUpperCase();
  el('ws-role').textContent = me.role || 'workspace';
  el('whoami').textContent = me.name || me.email || '—';
  el('avatar').textContent = (me.name || me.email || '·').charAt(0).toUpperCase();
}

async function loadTypes() {
  const result = await api('/events/types');
  if (!result.ok) return;
  const select = el('ev-type');
  const chosen = state.type;
  select.innerHTML = '<option value="all">All Events</option>' +
    (result.data.types || []).map((t) =>
      '<option value="' + escapeHtml(t.type) + '">' +
      escapeHtml(t.type) + ' (' + t.count + ')</option>').join('');
  select.value = chosen;
}

/* --------------------------------------------------------------------- */
function readUrl() {
  const p = new URLSearchParams(location.search);
  state.q = p.get('q') || '';
  state.type = p.get('type') || 'all';
  state.window = p.get('window') || 'all';
  state.page = Math.max(1, Number(p.get('page')) || 1);
  state.size = Number(p.get('size')) || 25;

  el('ev-q').value = state.q;
  el('ev-window').value = state.window;
  el('ev-size').value = String(state.size);
  el('ev-page').value = String(state.page);
}

function writeUrl() {
  const p = new URLSearchParams();
  if (state.q) p.set('q', state.q);
  if (state.type !== 'all') p.set('type', state.type);
  if (state.window !== 'all') p.set('window', state.window);
  if (state.page !== 1) p.set('page', String(state.page));
  if (state.size !== 25) p.set('size', String(state.size));
  const qs = p.toString();
  history.replaceState(null, '', '/events' + (qs ? '?' + qs : ''));
}

async function load() {
  writeUrl();
  const p = new URLSearchParams({
    q: state.q, type: state.type, window: state.window,
    page: String(state.page), size: String(state.size),
  });

  const result = await api('/events?' + p.toString());
  if (!result.ok) {
    note(el('msg'), result.error, 'error');
    state.rows = [];
    return render();
  }
  el('msg').hidden = true;

  state.rows = result.data.rows || [];
  state.total = result.data.total || 0;
  state.capped = !!result.data.capped;
  render();
}

/* --------------------------------------------------------------------- */
function stamp(seconds) {
  const d = new Date(seconds * 1000);
  const pad = (n) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
    ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
}

/* The Data column is a one-line summary, not a dump: the point is to scan a
   hundred rows, and the full payload is one click away in the drawer. */
function summarise(row) {
  const d = row.data || {};
  const parts = [];
  const push = (v) => { if (v !== undefined && v !== null && v !== '') parts.push(v); };

  switch (row.type) {
    case 'vehicleSpawned':
      push(d.model); push(d.plate);
      break;
    case 'playerKilled':
    case 'playerDamaged':
      push(d.weaponType);
      if (d.distance !== undefined && d.distance !== null) push(d.distance + 'm');
      break;
    case 'weaponFired':
      push(d.weaponType); if (d.hit) push('hit');
      break;
    case 'entityCreated':
      push(d.model); push(d.kind);
      break;
    case 'entityRemoved':
      push(d.model);
      break;
    case 'explosionEvent':
      push(d.explosionType !== undefined ? 'type ' + d.explosionType : null);
      if (d.invisible) push('invisible');
      break;
    case 'playerDropped':
      push(d.reason);
      break;
    case 'detection':
      push(d.signal); push(d.detail);
      break;
    default: {
      const keys = Object.keys(d).slice(0, 3);
      keys.forEach((k) => push(k + '=' + d[k]));
    }
  }

  return parts.length ? parts.join(' | ') : '–';
}

function render() {
  const pages = Math.max(1, Math.ceil(state.total / state.size));
  el('ev-shown').textContent = state.rows.length;
  el('ev-total').textContent = state.capped ? state.total + '+' : state.total;
  el('ev-pages').textContent = state.capped ? pages + '+' : pages;
  el('ev-page').value = String(state.page);
  el('ev-prev').disabled = state.page <= 1;
  el('ev-next').disabled = state.rows.length < state.size;

  COLUMNS.forEach((c) => {
    document.querySelectorAll('[data-col="' + c + '"]').forEach((n) => {
      n.hidden = state.hidden.has(c);
    });
  });

  const body = el('ev-body');
  const empty = el('ev-empty');

  if (!state.rows.length) {
    body.innerHTML = '';
    empty.hidden = false;
    empty.innerHTML = '<h3>No events matched</h3><p class="muted">' +
      (state.q
        ? 'Try a broader query, or widen the time range.'
        : 'Nothing has been recorded yet. Events start arriving once a server ' +
          'running NexusAC syncs with this workspace.') + '</p>';
    return;
  }

  empty.hidden = true;
  body.innerHTML = state.rows.map((row) => {
    const colour = colourFor(row.type);
    return '<tr data-id="' + row.id + '">' +
      '<td data-col="time" class="ev-time">' + stamp(row.at) + '</td>' +
      '<td data-col="type"><span class="ev-badge" style="--badge:' + colour + '">' +
        escapeHtml(row.type) + '</span></td>' +
      '<td data-col="data" class="ev-data">' + escapeHtml(summarise(row)) + '</td>' +
      '<td data-col="sender">' + who(row.senderName, row.sender) + '</td>' +
      '<td data-col="target">' + who(row.targetName, row.target) + '</td>' +
      '<td></td></tr>';
  }).join('');
}

/* A name that is also a link into Identities, because "who is this" is the very
   next question after "what happened". */
function who(name, uid) {
  if (!name && !uid) return '<span class="muted">–</span>';
  const label = escapeHtml(name || uid);
  if (!uid) return label;
  return '<a class="ev-who" href="/identities?q=' + encodeURIComponent(uid) + '" ' +
    'title="Look this account up in Identities">' + label + '</a>';
}

/* --------------------------------------------------------------------- */
function showRow(id) {
  const row = state.rows.find((r) => String(r.id) === String(id));
  if (!row) return;

  const body =
    '<dl class="id-facts">' +
      '<div><dt>Time</dt><dd>' + stamp(row.at) + '</dd></div>' +
      '<div><dt>Type</dt><dd>' + escapeHtml(row.type) + '</dd></div>' +
      '<div><dt>Sender</dt><dd>' + who(row.senderName, row.sender) + '</dd></div>' +
      '<div><dt>Target</dt><dd>' + who(row.targetName, row.target) + '</dd></div>' +
    '</dl>' +
    '<h4 class="ev-drawer-h">Payload</h4>' +
    '<pre class="ev-json">' + escapeHtml(JSON.stringify(row.data || {}, null, 2)) + '</pre>';

  Modal.show(body, null, 'EVENT', row.type);
}

/* --------------------------------------------------------------------- */
function buildColumnMenu() {
  const menu = el('ev-colmenu');
  menu.innerHTML = COLUMNS.map((c) =>
    '<label><input type="checkbox" data-toggle="' + c + '"' +
    (state.hidden.has(c) ? '' : ' checked') + '> ' + c + '</label>').join('');

  menu.addEventListener('change', (event) => {
    const box = event.target.closest('[data-toggle]');
    if (!box) return;
    const col = box.dataset.toggle;
    if (box.checked) state.hidden.delete(col); else state.hidden.add(col);
    try {
      localStorage.setItem('nx_ev_hidden', JSON.stringify([...state.hidden]));
    } catch (e) { /* private mode */ }
    render();
  });
}

/* --------------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  try {
    const saved = JSON.parse(localStorage.getItem('nx_ev_hidden') || '[]');
    if (Array.isArray(saved)) state.hidden = new Set(saved);
  } catch (e) { /* private mode */ }

  loadWorkspace();
  readUrl();
  buildColumnMenu();
  loadTypes();
  load();

  const go = () => {
    state.q = el('ev-q').value.trim();
    state.type = el('ev-type').value;
    state.window = el('ev-window').value;
    state.page = 1;
    load();
  };

  el('ev-go').addEventListener('click', go);
  el('ev-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  el('ev-type').addEventListener('change', go);
  el('ev-window').addEventListener('change', go);

  el('ev-size').addEventListener('change', () => {
    state.size = Number(el('ev-size').value) || 25;
    state.page = 1;
    load();
  });

  el('ev-prev').addEventListener('click', () => {
    if (state.page > 1) { state.page -= 1; load(); }
  });
  el('ev-next').addEventListener('click', () => { state.page += 1; load(); });
  el('ev-page').addEventListener('change', () => {
    state.page = Math.max(1, Number(el('ev-page').value) || 1);
    load();
  });

  el('ev-cols').addEventListener('click', (e) => {
    e.stopPropagation();
    const menu = el('ev-colmenu');
    menu.hidden = !menu.hidden;
  });
  document.addEventListener('click', () => { el('ev-colmenu').hidden = true; });
  el('ev-colmenu').addEventListener('click', (e) => e.stopPropagation());

  el('ev-body').addEventListener('click', (e) => {
    if (e.target.closest('a')) return;      // the Identities link wins
    const tr = e.target.closest('[data-id]');
    if (tr) showRow(tr.dataset.id);
  });

  // "/" focuses the query box, matching Identities and the in-game console.
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || Modal.open) return;
    const t = e.target;
    if (t && t.matches && t.matches('input, select, textarea')) return;
    e.preventDefault();
    el('ev-q').focus();
    el('ev-q').select();
  });
});
