/* Identities: search, alias traversal, and the account tree.

   Two modes share this page.

     search  what the query matched, paginated. No tree.
     alias   everything reachable from one identity through shared identifiers,
             with the tree drawn above it.

   The tree is laid out on an ellipse rather than force-simulated. A force layout
   looks better in a screenshot and worse in use: it settles differently every
   render, so a node is never where the investigator left it, and it costs a
   dependency and an animation loop for no analytical gain. Positions here are a
   pure function of the node ordering, so the same search always draws the same
   picture. */

const KIND_STYLE = {
  discord:  { label: 'Discord', colour: '#5865f2' }, steam: { label: 'Steam', colour: '#66c0f4' },
  fivem: { label: 'FiveM', colour: '#f40552' }, license: { label: 'License', colour: '#8b8b93' },
  license2: { label: 'License 2', colour: '#8b8b93' }, live: { label: 'Xbox Live', colour: '#0078d4' },
  xbl: { label: 'Xbox', colour: '#107c10' }, ip: { label: 'IP address', colour: '#e08b3c' },
  token: { label: 'Token', colour: '#a06ee1' }, device: { label: 'Device', colour: '#2fb2a4' }, name: { label: 'Name', colour: '#6b6b73' },
};
const BRAND_ICONS = {
  discord: '/static/brand/discord.svg',
  steam: '/static/brand/steam.svg',
  fivem: '/static/brand/fivem.svg',
};
const KIND_GLYPHS = { license: 'key', license2: 'key', ip: 'server', device: 'shield-check', token: 'key' };

function identifierIcon(kind) {
  const brand = BRAND_ICONS[kind];
  if (brand) return '<img class="id-platform-icon" src="' + brand + '" alt="">';
  return '<span class="id-platform-glyph" aria-hidden="true">' + icon(KIND_GLYPHS[kind] || 'server', 14) + '</span>';
}

function identifierValue(kind, value, compact) {
  if (!value) return '—';
  const full = String(value);
  const shown = compact && full.length > 24 ? full.slice(0, 10) + '…' + full.slice(-8) : full;
  return '<span class="id-live-id" title="' + escapeHtml(full) + '">' + identifierIcon(kind) +
    '<code>' + escapeHtml(shown) + '</code></span>';
}

const state = {
  mode: 'search',
  query: '',
  page: 1,
  size: 25,
  total: 0,
  rows: [],
  root: null,
  edges: [],
  suppressed: [],
  truncated: false,
  treeHidden: false,
  selected: null,
  onlinePlayers: [],
  onlineServers: 0,
  detail: null,
};

const el = (id) => document.getElementById(id);

/* --------------------------------------------------------------------- *
 * Sidebar identity, so the page does not look half-loaded
 * --------------------------------------------------------------------- */
async function loadWorkspace() {
  const result = await api('/workspace');
  if (!result.ok) return;
  const me = result.data.user || {};
  // /workspace returns the id on the user and the names in a list, so the
  // current one has to be matched out rather than read directly.
  const current = (result.data.workspaces || []).find((w) => w.id === me.workspace);
  const name = (current && current.name) || 'Workspace';

  el('ws-name').firstChild.textContent = name;
  el('ws-initial').textContent = name.charAt(0).toUpperCase();
  el('ws-role').textContent = me.role || 'workspace';
}

/* --------------------------------------------------------------------- *
 * Fetching
 * --------------------------------------------------------------------- */
async function runSearch(push) {
  const q = el('id-q').value.trim();
  state.mode = 'search';
  state.query = q;
  state.root = null;
  state.edges = [];
  state.suppressed = [];

  const result = await api(
    '/identities?q=' + encodeURIComponent(q) + '&page=' + state.page + '&size=' + state.size
  );
  if (!result.ok) return fail(result.error);

  state.rows = result.data.results || [];
  state.total = result.data.total || 0;
  el('id-hint').textContent = describeMatch(result.data);
  loadSummary();

  if (push) {
    const url = q ? '/identities?q=' + encodeURIComponent(q) : '/identities';
    history.replaceState(null, '', url);
  }
  render();
}

async function loadSummary() {
  const result = await api('/identities/summary');
  if (!result.ok) return;
  const summary = result.data;
  el('id-stat-total').textContent = Number(summary.total || 0).toLocaleString();
  el('id-stat-recent').textContent = Number(summary.recent || 0).toLocaleString();
  el('id-stat-sessions').textContent = Number(summary.sessions || 0).toLocaleString();
  el('id-stat-flagged').textContent = Number(summary.flagged || 0).toLocaleString();
}

async function runAliases(uid) {
  const result = await api('/identities/aliases?uid=' + encodeURIComponent(uid));
  if (!result.ok) return fail(result.error);

  state.mode = 'alias';
  state.root = result.data.root;
  state.rows = result.data.nodes || [];
  state.edges = result.data.edges || [];
  state.suppressed = result.data.suppressed || [];
  state.truncated = !!result.data.truncated;
  state.total = state.rows.length;
  state.page = 1;
  state.selected = uid;

  el('id-hint').textContent =
    'Alias search: every account reachable from this identity through a shared identifier.';
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function describeMatch(data) {
  if (data.matched === 'identifier') {
    const kinds = (data.kinds || []).map((k) => (KIND_STYLE[k] || {}).label || k);
    return 'Read as ' + (kinds.join(' or ') || 'an identifier') + '.';
  }
  if (data.matched === 'name') return 'No identifier format matched, so this was searched as a name.';
  return 'The most recently seen accounts in this workspace.';
}

function fail(message) {
  note(el('msg'), message, 'error');
  state.rows = [];
  render();
}

async function loadOnlinePlayers() {
  const result = await api('/identities/online');
  if (!result.ok) {
    el('id-live-count').textContent = result.error || 'Unavailable';
    el('id-live-rows').innerHTML = '<tr><td colspan="11" class="muted">Live network data is unavailable.</td></tr>';
    return;
  }
  state.onlinePlayers = result.data.players || [];
  state.onlineServers = result.data.servers || 0;
  renderOnlinePlayers();
  if (state.rows.length) render();
}

function renderOnlinePlayers() {
  const query = el('id-q').value.trim().toLowerCase();
  const players = state.onlinePlayers.filter((player) => {
    const net = player.network || {};
    const identifiers = net.identifiers || [];
    const values = identifiers.map((entry) => (entry.kind || '') + ':' + (entry.value || '')).join(' ');
    return !query || [player.name, player.server, player.src, net.ip || '', values]
      .some((value) => String(value).toLowerCase().includes(query));
  });
  el('id-live-count').textContent = players.length + ' online · ' +
    state.onlineServers + ' server' + (state.onlineServers === 1 ? '' : 's') + ' · auto-refresh 5s';
  const byKind = (player, kinds) => {
    const net = player.network || {};
    const entry = (net.identifiers || []).find((item) => kinds.includes(item.kind));
    return entry ? entry.value : '';
  };
  el('id-live-rows').innerHTML = players.length ? players.map((player) => {
    const license = byKind(player, ['license2', 'license']);
    const net = player.network || {};
    const identity = (net.identifiers || []).find((item) => item.kind === 'discord');
    const discord = identity ? identity.value : '';
    const steam = byKind(player, ['steam']);
    const fivem = byKind(player, ['fivem']);
    const device = byKind(player, ['device']);
    const otherIds = (net.identifiers || []).filter((entry) =>
      !['discord', 'steam', 'fivem', 'license', 'license2', 'device'].includes(entry.kind)
    ).map((entry) => '<span class="id-live-id"><span class="id-live-kind">' + escapeHtml(entry.kind) +
      '</span>' + identifierIcon(entry.kind) + '<code>' + escapeHtml(String(entry.value || '').slice(0, 24)) + '</code></span>').join('') || '—';
    return '<tr><td><b>' + escapeHtml(player.name || 'Unknown') + '</b><small class="muted">ID ' +
      escapeHtml(player.src == null ? '—' : player.src) + (player.risk ? ' · risk ' + escapeHtml(player.risk) : '') + '</small></td>' +
      '<td>' + escapeHtml(player.server || '—') + '</td><td>' + identifierValue('discord', discord) + '</td>' +
      '<td>' + identifierValue('steam', steam) + '</td><td>' + identifierValue('fivem', fivem) + '</td>' +
      '<td>' + identifierValue('license', license, true) + '</td><td>' + identifierValue('device', device, true) + '</td>' +
      '<td class="id-live-other">' + otherIds + '</td><td>' + identifierValue('ip', net.ip, true) + '</td>' +
      '<td>' + escapeHtml(player.ping == null ? '—' : player.ping + ' ms') + '</td>' +
      '<td>' + escapeHtml(formatSession(player.sessionAge)) + '</td></tr>';
  }).join('') : '<tr><td colspan="11" class="muted">' +
    (state.onlinePlayers.length ? 'No live players match this search.' : 'No players are connected to an online server.') + '</td></tr>';
}

function formatSession(value) {
  const seconds = Math.max(0, Number(value) || 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? hours + 'h ' + minutes + 'm' : minutes + 'm';
}

/* --------------------------------------------------------------------- *
 * Rendering
 * --------------------------------------------------------------------- */
function render() {
  const grid = el('id-grid');
  const empty = el('id-empty');
  const toolbar = el('id-toolbar');

  toolbar.hidden = false;

  const shown = state.rows.length;
  const from = state.mode === 'alias' ? 1 : (state.page - 1) * state.size + 1;
  const to = state.mode === 'alias' ? shown : from + shown - 1;
  el('id-count').textContent = shown
    ? 'Showing ' + from + '-' + to + ' of ' + state.total + ' result' + (state.total === 1 ? '' : 's')
    : 'No results';

  const pages = state.mode === 'alias' ? 1 : Math.max(1, Math.ceil(state.total / state.size));
  el('id-page').textContent = state.page;
  el('id-pages').textContent = pages;
  el('id-prev').disabled = state.mode === 'alias' || state.page <= 1;
  el('id-next').disabled = state.mode === 'alias' || state.page >= pages;
  el('id-size').disabled = state.mode === 'alias';

  drawTree();

  if (!shown) {
    grid.innerHTML = '';
    empty.hidden = false;
    empty.innerHTML =
      '<h3>Nothing found</h3>' +
      '<p class="muted">Check the identifier is right, or try a different one. ' +
      'An account only appears here once a server running NexusAC has seen it.</p>';
    return;
  }

  empty.hidden = true;
  grid.innerHTML = state.rows.map(rowHTML).join('');
  if (state.selected && state.rows.some((row) => row.uid === state.selected)) loadDetail(state.selected);
}

function rowHTML(row) {
  const selected = row.uid === state.selected ? ' selected' : '';
  const hash = row.uid.includes(':') ? row.uid.split(':').slice(1).join(':') : row.uid;
  const live = liveFor(row);
  const marks = Object.entries(row.kinds || {}).filter(([kind]) => kind !== 'name');
  const chips = marks.slice(0, 5).map(([kind, values]) => '<span class="id-platform-chip" title="' + escapeHtml((KIND_STYLE[kind] || {}).label || kind) + ': ' + escapeHtml(values[0]) + '">' + identifierIcon(kind) + '<span>' + escapeHtml((KIND_STYLE[kind] || {}).label || kind) + '</span><b>' + values.length + '</b></span>').join('');
  return '<tr class="id-directory-row' + selected + '" data-uid="' + escapeHtml(row.uid) + '"><td><input type="checkbox" class="id-row-select" aria-label="Select ' + escapeHtml(row.name) + '"></td><td><button class="id-player-select" data-select="' + escapeHtml(row.uid) + '"><span class="id-avatar">' + icon('users', 19) + '</span><span><b>' + escapeHtml(row.name) + '</b><small title="' + escapeHtml(row.uid) + '">' + escapeHtml(hash) + '</small></span></button></td><td><div class="id-chip-list">' + (chips || '<span class="muted">No identifiers stored</span>') + (marks.length > 5 ? '<span class="id-more">+' + (marks.length - 5) + '</span>' : '') + '</div></td><td><b>' + escapeHtml(ago(row.lastSeen)) + '</b><small>' + escapeHtml(new Date(Number(row.lastSeen) * 1000).toLocaleString()) + '</small></td><td><span class="id-presence ' + (live ? 'online' : 'offline') + '"><i></i>' + (live ? 'Online' : 'Offline') + '</span>' + (row.banned ? '<small class="id-flagged">Flagged</small>' : '') + '</td><td><button class="id-row-action" data-alias="' + escapeHtml(row.uid) + '" title="Find linked accounts" aria-label="Find linked accounts">' + icon('braces', 16) + '</button><button class="id-row-action" data-expand="' + escapeHtml(row.uid) + '" title="Open player details" aria-label="Open player details">' + icon('arrow-up-right', 16) + '</button></td></tr>';
}

function liveFor(row) {
  const marks = row.kinds || {};
  return state.onlinePlayers.find((player) => {
    const ids = (player.network || {}).identifiers || [];
    return ids.some((entry) => (marks[entry.kind] || []).includes(entry.value));
  });
}

/* --------------------------------------------------------------------- *
 * The tree
 * --------------------------------------------------------------------- */
function drawTree() {
  const panel = el('id-tree-panel');
  if (state.mode !== 'alias' || state.treeHidden || state.rows.length < 2) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;

  const svg = el('id-tree');
  const nodes = state.rows;
  const n = nodes.length;
  const cx = 500, cy = 280;
  const rx = Math.min(420, 150 + n * 9);
  const ry = Math.min(230, 90 + n * 6);

  const at = {};
  nodes.forEach((node, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    at[node.uid] = { x: cx + Math.cos(angle) * rx, y: cy + Math.sin(angle) * ry, angle };
  });

  const lines = state.edges.map((edge) => {
    const a = at[edge.a], b = at[edge.b];
    if (!a || !b) return '';
    // Hardware and account identifiers are stronger evidence than a shared IP,
    // so the edge says so rather than drawing every link identically.
    const strong = edge.kinds.some((k) => k === 'device' || k === 'token' || k === 'license2');
    return '<line class="id-edge' + (strong ? ' strong' : '') + '" ' +
      'x1="' + a.x.toFixed(1) + '" y1="' + a.y.toFixed(1) + '" ' +
      'x2="' + b.x.toFixed(1) + '" y2="' + b.y.toFixed(1) + '">' +
      '<title>' + escapeHtml(edge.kinds.map((k) => (KIND_STYLE[k] || {}).label || k).join(', ')) +
      '</title></line>';
  }).join('');

  const dots = nodes.map((node) => {
    const p = at[node.uid];
    const right = Math.cos(p.angle) >= 0;
    const cls = 'id-node' + (node.uid === state.root ? ' root' : '') +
      (node.banned ? ' banned' : '') + (node.uid === state.selected ? ' selected' : '');
    return '<g class="' + cls + '" data-node="' + escapeHtml(node.uid) + '">' +
      '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="6"/>' +
      '<text x="' + (p.x + (right ? 11 : -11)).toFixed(1) + '" y="' + (p.y + 4).toFixed(1) + '" ' +
        'text-anchor="' + (right ? 'start' : 'end') + '">' +
        escapeHtml(node.name.length > 18 ? node.name.slice(0, 17) + '…' : node.name) +
      '</text><title>' + escapeHtml(node.name + ' · ' + node.uid) + '</title></g>';
  }).join('');

  svg.innerHTML = lines + dots;

  const note = [];
  note.push(n + ' linked account' + (n === 1 ? '' : 's'));
  if (state.truncated) note.push('stopped at the ' + n + '-account limit');
  if (state.suppressed.length) {
    note.push(state.suppressed.length + ' identifier' +
      (state.suppressed.length === 1 ? '' : 's') + ' ignored as too widely shared');
  }
  el('id-tree-note').textContent = note.join(' · ');

  el('id-tree-legend').innerHTML = state.suppressed.length
    ? '<b>Ignored as hubs:</b> ' + state.suppressed.map((s) =>
        '<span class="id-sup">' + escapeHtml(((KIND_STYLE[s.kind] || {}).label || s.kind) +
        ' ' + s.value) + ' <i>' + s.holders + ' accounts</i></span>').join('')
    : '';
}

/* --------------------------------------------------------------------- *
 * Detail drawer
 * --------------------------------------------------------------------- */
async function loadDetail(uid) {
  if (state.detail && state.detail.uid === uid) { renderDetail(state.detail); return; }
  const result = await api('/identities/detail?uid=' + encodeURIComponent(uid));
  if (!result.ok) return fail(result.error);
  state.detail = result.data;
  renderDetail(state.detail);
}

function renderDetail(row) {
  const groups = {};
  (row.marks || []).forEach((mark) => {
    (groups[mark.kind] = groups[mark.kind] || []).push(mark);
  });

  const player = liveFor(row);
  const panel = el('id-detail-panel');
  panel.innerHTML = '<div class="id-detail-top"><div class="id-avatar large">' + icon('users', 24) + '</div><div class="id-detail-name"><span class="eyebrow">PLAYER INFORMATION</span><h3>' + escapeHtml(row.name) + '</h3><span class="id-presence ' + (player ? 'online' : 'offline') + '"><i></i>' + (player ? 'Online' : 'Offline') + '</span></div></div>' +
    '<div class="id-detail-actions"><b>Quick actions</b><button class="button" data-alias="' + escapeHtml(row.uid) + '">' + icon('braces', 15) + ' Investigate linked accounts</button></div>' +
    '<section class="id-detail-section"><h4>' + icon('key', 15) + ' Identifiers <span>' + (row.marks || []).length + '</span></h4>' +
      (row.marks || []).map((mark) => '<div class="id-detail-mark"><span>' + identifierIcon(mark.kind) + '<b>' + escapeHtml((KIND_STYLE[mark.kind] || {}).label || mark.kind) + '</b></span><code title="' + escapeHtml(mark.value) + '">' + escapeHtml(mark.value) + '</code><button class="id-copy" data-copy="' + escapeHtml(mark.value) + '" title="Copy identifier" aria-label="Copy identifier">' + icon('key', 14) + '</button></div>').join('') + '</section>' +
    '<section class="id-detail-section"><h4>' + icon('activity', 15) + ' Activity</h4><dl class="id-facts">' + fact('First seen', ago(row.firstSeen)) + fact('Last seen', ago(row.lastSeen)) + fact('Sessions', Number(row.sessions || 0).toLocaleString()) + fact('Server', player ? escapeHtml(player.server) : 'Offline') + '</dl></section>' +
    (row.banned ? '<div class="id-detail-warning">' + icon('shield', 16) + '<span><b>Flagged account</b><small>' + escapeHtml(row.reason || 'No reason recorded') + '</small></span></div>' : '');
}

function fact(label, value) {
  return '<div><dt>' + escapeHtml(label) + '</dt><dd>' + value + '</dd></div>';
}

/* --------------------------------------------------------------------- *
 * Wiring
 * --------------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  loadWorkspace();

  const input = el('id-q');
  let timer = null;

  input.addEventListener('input', () => {
    renderOnlinePlayers();
    clearTimeout(timer);
    timer = setTimeout(() => { state.page = 1; runSearch(true); }, 280);
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      clearTimeout(timer);
      state.page = 1;
      runSearch(true);
    }
  });

  // "/" focuses the search from anywhere, the way the rest of the console does.
  document.addEventListener('keydown', (event) => {
    if (event.key !== '/' || Modal.open) return;
    const target = event.target;
    if (target && target.matches && target.matches('input, select, textarea')) return;
    event.preventDefault();
    input.focus();
    input.select();
  });

  el('id-grid').addEventListener('click', (event) => {
    const alias = event.target.closest('[data-alias]');
    if (alias) return runAliases(alias.dataset.alias);
    const expand = event.target.closest('[data-expand]');
    const select = event.target.closest('[data-select]');
    if (expand || select) { state.selected = (expand || select).dataset.expand || (expand || select).dataset.select; state.detail = null; render(); }
  });
  el('id-detail-panel').addEventListener('click', async (event) => {
    const copy = event.target.closest('[data-copy]');
    if (copy) { try { await navigator.clipboard.writeText(copy.dataset.copy); note(el('msg'), 'Identifier copied.', 'success'); } catch (_) { note(el('msg'), 'Clipboard access is unavailable in this browser.', 'error'); } }
    const alias = event.target.closest('[data-alias]');
    if (alias) runAliases(alias.dataset.alias);
  });

  el('id-tree').addEventListener('click', (event) => {
    const node = event.target.closest('[data-node]');
    if (!node) return;
    state.selected = node.dataset.node;
    render();
    const card = document.querySelector('.id-directory-row.selected');
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  el('id-tree-toggle').addEventListener('click', () => {
    state.treeHidden = !state.treeHidden;
    el('id-tree-toggle').querySelector('span').textContent =
      state.treeHidden ? 'Show account tree' : 'Hide account tree';
    drawTree();
  });

  el('id-prev').addEventListener('click', () => {
    if (state.page > 1) { state.page -= 1; runSearch(false); }
  });
  el('id-next').addEventListener('click', () => { state.page += 1; runSearch(false); });
  el('id-size').addEventListener('change', () => {
    state.size = Number(el('id-size').value) || 25;
    state.page = 1;
    runSearch(false);
  });

  el('id-live-refresh').addEventListener('click', loadOnlinePlayers);
  el('id-export').addEventListener('click', () => {
    const lines = [['name','uid','firstSeen','lastSeen','sessions','banned','kind','value'].join(',')];
    state.rows.forEach((row) => Object.entries(row.kinds || {}).forEach(([kind, values]) => values.forEach((value) => {
      lines.push([row.name,row.uid,row.firstSeen,row.lastSeen,row.sessions,row.banned,kind,value].map((field) => '"' + String(field == null ? '' : field).replace(/"/g, '""') + '"').join(','));
    })));
    const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const href = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = href; link.download = 'nexus-identities.csv'; link.click(); URL.revokeObjectURL(href);
  });
  el('id-select-all').addEventListener('change', (event) => document.querySelectorAll('.id-row-select').forEach((box) => { box.checked = event.target.checked; }));

  runSearch(false);
  loadOnlinePlayers();
  window.setInterval(loadOnlinePlayers, 5000);
});
