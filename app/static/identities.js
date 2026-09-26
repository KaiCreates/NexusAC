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
  discord:  { label: 'Discord',  short: 'D', colour: '#5865f2' },
  steam:    { label: 'Steam',    short: 'S', colour: '#66c0f4' },
  fivem:    { label: 'Cfx',      short: 'C', colour: '#f40552' },
  license:  { label: 'License',  short: 'L', colour: '#8b8b93' },
  license2: { label: 'License2', short: 'L', colour: '#8b8b93' },
  live:     { label: 'Live',     short: 'W', colour: '#0078d4' },
  xbl:      { label: 'Xbox',     short: 'X', colour: '#107c10' },
  ip:       { label: 'IP',       short: 'I', colour: '#e08b3c' },
  token:    { label: 'Token',    short: 'T', colour: '#a06ee1' },
  device:   { label: 'Device',   short: 'H', colour: '#2fb2a4' },
  name:     { label: 'Name',     short: 'N', colour: '#6b6b73' },
};

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

  if (push) {
    const url = q ? '/identities?q=' + encodeURIComponent(q) : '/identities';
    history.replaceState(null, '', url);
  }
  render();
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
  grid.innerHTML = state.rows.map(card).join('');
}

function card(row) {
  const selected = row.uid === state.selected ? ' selected' : '';
  const root = row.uid === state.root ? ' root' : '';
  const hash = row.uid.includes(':') ? row.uid.split(':').slice(1).join(':') : row.uid;

  const badges = [];
  Object.keys(row.kinds || {}).forEach((kind) => {
    const style = KIND_STYLE[kind];
    if (!style || kind === 'name') return;
    row.kinds[kind].forEach((value) => {
      badges.push(
        '<span class="id-badge" style="--badge:' + style.colour + '" ' +
        'title="' + escapeHtml(style.label + ': ' + value) + '">' + style.short + '</span>'
      );
    });
  });

  return (
    '<article class="id-card' + selected + root + '" data-uid="' + escapeHtml(row.uid) + '">' +
      '<div class="id-card-main">' +
        '<h3>' + escapeHtml(row.name) +
          (row.banned ? ' <span class="id-warn" title="' +
            escapeHtml(row.reason || 'Banned') + '">&#9888;</span>' : '') +
        '</h3>' +
        '<p class="id-uid" title="' + escapeHtml(row.uid) + '">' + escapeHtml(hash) + '</p>' +
        '<div class="id-badges">' + (badges.join('') || '<span class="muted">no identifiers</span>') + '</div>' +
      '</div>' +
      '<div class="id-card-side">' +
        '<button class="id-card-btn" data-expand="' + escapeHtml(row.uid) + '" ' +
          'title="Everything known about this account">&#10530;</button>' +
        '<button class="id-card-btn" data-alias="' + escapeHtml(row.uid) + '" ' +
          'title="Find accounts sharing identifiers with this one">' + icon('search', 15) + '</button>' +
      '</div>' +
    '</article>'
  );
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
async function showDetail(uid) {
  const result = await api('/identities/detail?uid=' + encodeURIComponent(uid));
  if (!result.ok) return fail(result.error);
  const row = result.data;

  const groups = {};
  (row.marks || []).forEach((mark) => {
    (groups[mark.kind] = groups[mark.kind] || []).push(mark);
  });

  const body =
    '<dl class="id-facts">' +
      fact('First seen', ago(row.firstSeen)) +
      fact('Last seen', ago(row.lastSeen)) +
      fact('Sessions', row.sessions) +
      fact('Identifiers', row.markCount) +
      (row.banned ? fact('Banned', escapeHtml(row.reason || 'no reason recorded')) : '') +
    '</dl>' +
    Object.keys(groups).sort().map((kind) => {
      const style = KIND_STYLE[kind] || { label: kind, colour: '#6b6b73' };
      return '<section class="id-marks">' +
        '<h4><span class="id-badge" style="--badge:' + style.colour + '">' +
          (style.short || '?') + '</span>' + escapeHtml(style.label) + '</h4>' +
        groups[kind].map((mark) =>
          '<div class="id-mark"><code>' + escapeHtml(mark.value) + '</code>' +
          '<span class="muted">seen ' + mark.seen + '× · last ' + ago(mark.lastSeen) + '</span></div>'
        ).join('') +
      '</section>';
    }).join('') +
    '<div class="button-row">' +
      '<button class="button light small" data-drawer-alias="' + escapeHtml(uid) + '">' +
        icon('search', 15) + ' Find alias accounts</button>' +
    '</div>';

  Modal.show(body, (dialog) => {
    const button = dialog.querySelector('[data-drawer-alias]');
    if (button) {
      button.addEventListener('click', () => {
        Modal.close();
        runAliases(uid);
      });
    }
  }, row.banned ? 'BANNED ACCOUNT' : 'ACCOUNT', row.name);
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
    if (expand) return showDetail(expand.dataset.expand);
    const card = event.target.closest('[data-uid]');
    if (card) { state.selected = card.dataset.uid; render(); }
  });

  el('id-tree').addEventListener('click', (event) => {
    const node = event.target.closest('[data-node]');
    if (!node) return;
    state.selected = node.dataset.node;
    render();
    const card = document.querySelector('.id-card.selected');
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

  runSearch(false);
});
