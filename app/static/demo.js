/* The interactive live demo, ported from the Next.js build's components/dashboard.tsx.
   Same markup and class names, same simulated behaviour — no React. */

let state = createDemoState();
let active = 'overview';
let search = '';
let category = 'All';
let period = '24 hours';
let toastTimer = null;

const root = document.getElementById('demo-root');
const esc = escapeHtml;

/* ------------------------------------------------------------------ helpers */

const server = () => state.servers.find((s) => s.id === state.selectedServer) || state.servers[0];
const protectionsOf = () => state.protections[server().id] || [];
const enabledCount = () => protectionsOf().filter((p) => p.enabled).length;
const serverDetections = () => state.detections.filter((d) => d.serverId === server().id);
const bansOf = () => serverDetections().filter((d) => d.action === 'Banned' && !state.revoked.includes(d.id));
const activityOf = () => state.activity.filter((a) => a.serverId === server().id);

function badge(text, tone) {
  return '<span class="badge ' + (tone || 'neutral') + '">' + text + '</span>';
}
function toggle(label, on, data) {
  return '<button type="button" role="switch" aria-checked="' + (on ? 'true' : 'false') +
    '" aria-label="' + esc(label) + '" class="toggle ' + (on ? 'on' : '') + '" ' + (data || '') +
    '><span></span></button>';
}
function empty(text) {
  return '<div class="empty-state">' + icon('scan-line', 26) + '<h3>All clear here.</h3><p>' +
    esc(text || 'No records match your filters.') + '</p></div>';
}
function toast(message) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();
  const node = document.createElement('div');
  node.className = 'toast';
  node.setAttribute('role', 'status');
  node.innerHTML = ICONS.check + esc(message);
  document.body.appendChild(node);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.remove(), 3600);
}
function dispatch(action) {
  state = demoReduce(state, action);
  render();
}
function navigate(section) {
  active = section;
  history.replaceState({}, '', section === 'overview' ? '/demo' : '/demo/' + section);
  document.title = SECTION_LABELS[section] + ' — NexusAC demo';
  render();
}

/* ------------------------------------------------------------- shared blocks */

function detectionTable(rows, compact) {
  if (!rows.length) return empty();
  return '<div class="table-scroll"><table><thead><tr>' +
    '<th>Player</th><th>Detection</th>' + (compact ? '' : '<th>Confidence</th>') +
    '<th>Action</th><th>Time</th><th><span class="sr-only">Investigate</span></th>' +
    '</tr></thead><tbody>' + rows.map((d) =>
      '<tr><td><button class="player-cell" data-investigate="' + d.id + '">' +
        '<span class="avatar">' + esc(d.player.slice(0, 1)) + '</span>' +
        '<span><b>' + esc(d.player) + '</b><small>ID ' + d.playerId + '</small></span></button></td>' +
      '<td><span>' + esc(d.kind) + '</span><small>' + esc(d.category) + '</small></td>' +
      (compact ? '' : '<td><div class="confidence"><span>' + d.confidence + '%</span>' +
        '<i style="width:' + (d.confidence / 2) + 'px"></i></div></td>') +
      '<td>' + badge(d.action, d.action === 'Banned' ? 'danger'
        : d.action === 'Flagged' ? 'warning' : 'neutral') + '</td>' +
      '<td class="mono muted">' + esc(d.time) + '</td>' +
      '<td><button class="icon-button" aria-label="Investigate ' + d.id + '" data-investigate="' +
        d.id + '">' + icon('arrow-up-right', 15) + '</button></td></tr>').join('') +
    '</tbody></table></div>';
}

function filterBar() {
  const cats = ['All', 'Combat', 'Injection', 'Events', 'Entities', 'Weapons'];
  return '<div class="filter-bar"><div class="filter-tabs" aria-label="Detection categories">' +
    cats.map((c) => '<button data-category="' + c + '" aria-pressed="' + (category === c) + '"' +
      (category === c ? ' class="active"' : '') + '>' + c + '</button>').join('') +
    '</div><label class="search-field">' + icon('search', 15) +
    '<input id="search" aria-label="Search detections" placeholder="Search player or detection…" ' +
    'value="' + esc(search) + '"></label></div>';
}

/* ------------------------------------------------------------------ sections */

function sectionOverview() {
  const s = server();
  const protections = protectionsOf();
  const enabled = enabledCount();
  const detections = serverDetections();
  const health = protections.length ? Math.round((enabled / protections.length) * 100) : 0;
  const stats = [
    ['Active players', s.players, 'of ' + s.capacity + ' player slots', 'users'],
    ['Detections', detections.length, 'In this sample dataset', 'scan-line'],
    ['Active bans', bansOf().length, 'Evidence attached', 'ban'],
    ['Server uptime', s.uptime, s.online ? 'Heartbeat healthy · ' + s.latency + ' ms'
      : 'Heartbeat unavailable', 'activity'],
  ];
  const path = period === '24 hours'
    ? 'M0 127 L25 121 L48 125 L72 110 L96 119 L120 107 L145 113 L165 92 L180 105 L205 93 L225 106 L250 66 L270 92 L292 83 L315 96 L335 79 L350 33 L365 78 L390 63 L410 81 L430 67 L450 79 L470 60 L492 72 L510 17 L525 59 L550 40 L568 59 L590 44 L610 58 L632 35 L660 48 L660 145 L0 145 Z'
    : 'M0 135 L40 128 L80 102 L120 111 L160 94 L200 99 L240 53 L280 69 L320 81 L360 40 L400 57 L440 61 L480 34 L520 52 L560 27 L610 42 L660 20 L660 145 L0 145 Z';
  const xLabels = period === '24 hours'
    ? ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00']
    : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const activity = activityOf();

  return '<div class="stats-grid">' + stats.map((c) =>
      '<article class="panel stat"><span>' + esc(c[0]) + icon(c[3], 14) + '</span>' +
      '<strong>' + esc(c[1]) + '</strong><small>' + esc(c[2]) + '</small></article>').join('') +
    '</div>' +

    '<div class="overview-middle"><section class="panel chart-panel">' +
    '<div class="panel-heading"><div><h3>Detection activity</h3>' +
    '<p>Sample threat signals over ' + esc(period) + '</p></div>' +
    '<span class="chart-legend"><i></i> Detections</span></div>' +
    '<div class="chart"><div class="chart-y"><span>40</span><span>30</span><span>20</span>' +
    '<span>10</span><span>0</span></div><div class="chart-plot">' +
    '<svg viewBox="0 0 660 145" preserveAspectRatio="none" role="img" ' +
    'aria-label="Illustrative detections trend over ' + esc(period) + '">' +
    '<defs><linearGradient id="area-full" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0%" stop-color="#fff" stop-opacity=".18"/>' +
    '<stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>' +
    [5, 40, 75, 110, 144].map((y) =>
      '<line x1="0" y1="' + y + '" x2="660" y2="' + y + '" stroke="#ffffff0b" stroke-dasharray="3 4"/>').join('') +
    '<path d="' + path + '" fill="url(#area-full)" stroke="#c4c4ce" stroke-width="1.7" ' +
    'stroke-linejoin="round"/></svg>' +
    '<div class="chart-x">' + xLabels.map((t) => '<span>' + t + '</span>').join('') + '</div>' +
    '</div></div></section>' +

    '<section class="panel health-panel"><div class="panel-heading"><h3>Protection health</h3>' +
    icon('shield-check', 17) + '</div>' +
    '<div class="health-value">' + health + '<span>%</span>' +
    badge(enabled === protections.length ? 'All systems ready' : 'Review modules',
          enabled === protections.length ? 'success' : 'warning') + '</div>' +
    '<div class="health-bars">' + protections.map((p) =>
      '<i class="' + (p.enabled ? 'enabled' : '') + '"></i>').join('') + '</div>' +
    '<p>' + enabled + ' of ' + protections.length + ' modules enabled</p>' +
    protections.filter((p) => p.category === 'Server').slice(0, 3).map((p) =>
      '<div class="health-row"><span>' + esc(p.name) + '</span>' +
      toggle(p.name, p.enabled, 'data-protect="' + esc(p.name) + '"') + '</div>').join('') +
    '<button class="text-link" data-go="protection">Manage protections ' +
    icon('arrow-right', 13) + '</button></section></div>' +

    '<div class="overview-bottom"><section class="panel recent-panel">' +
    '<div class="panel-heading"><h3>Recent detections <span class="muted">' +
    detections.length + '</span></h3>' +
    '<button class="text-link" data-go="detections">View all ' + icon('arrow-up-right', 13) +
    '</button></div>' + detectionTable(detections.slice(0, 4), true) + '</section>' +

    '<section class="panel activity-panel"><div class="panel-heading">' +
    '<h3>Live activity <span class="live-label">LIVE</span></h3>' +
    '<button class="icon-button" data-stream aria-label="' +
    (state.stream ? 'Pause live activity' : 'Resume live activity') + '">' +
    icon(state.stream ? 'pause' : 'play', 13) + '</button></div>' +
    '<div class="activity-list">' + (activity.length
      ? activity.slice(0, 4).map((a, i) =>
        '<div class="activity-item"><span class="activity-point ' + (i === 0 ? 'latest' : '') +
        '"></span><div>' + esc(a.text) + '<small>' + esc(a.time) + '</small></div></div>').join('')
      : '<p class="muted">No activity for this server.</p>') + '</div>' +
    '<div class="feed-footer">' + icon('radio', 12) +
    (state.stream ? 'Simulated updates every 5 seconds' : 'Feed paused') + '</div></section></div>' +

    '<div class="dashboard-footnote">' + icon('lock', 11) +
    ' Demo data only. Changes stay in this session.<span>' + icon('wifi', 11) + ' ' +
    (s.online ? s.latency + ' ms heartbeat' : 'Server offline') + ' · ' + s.blocked +
    ' blocked events</span></div>';
}

function sectionServers() {
  return '<div class="server-cards">' + state.servers.map((s) =>
    '<article class="panel server-card"><div class="panel-heading">' +
    '<span class="feature-icon">' + icon('server', 21) + '</span>' +
    badge(s.online ? 'Online' : 'Offline', s.online ? 'success' : 'neutral') + '</div>' +
    '<h3>' + esc(s.name) + '</h3><p>' + esc(s.region) + ' · ' + esc(s.id) + '</p>' +
    '<dl class="detail-list">' +
    '<div><dt>Players</dt><dd>' + s.players + ' / ' + s.capacity + '</dd></div>' +
    '<div><dt>Uptime</dt><dd>' + esc(s.uptime) + '</dd></div>' +
    '<div><dt>Heartbeat</dt><dd>' + (s.online ? s.latency + ' ms' : 'Unavailable') + '</dd></div>' +
    '<div><dt>Configuration</dt><dd>' + (s.online ? 'Synced · v24' : 'Pending connection') +
    '</dd></div></dl>' +
    '<button class="button" data-open-server="' + esc(s.id) + '">Open server ' +
    icon('arrow-up-right', 14) + '</button></article>').join('') + '</div>';
}

function sectionPlayers() {
  const s = server();
  const detections = serverDetections();
  let people = [];
  if (s.online) {
    people = [{ name: 'Kai', id: 24 }, { name: 'Luna', id: 58 }, { name: 'River', id: 84 }]
      .concat(detections.map((d) => ({ name: d.player, id: d.playerId })))
      .filter((p, i, a) => a.findIndex((v) => v.id === p.id) === i)
      .filter((p) => (p.name + ' ' + p.id).toLowerCase().includes(search.toLowerCase()));
  }
  const banned = bansOf();
  return '<section class="panel"><div class="panel-heading">' +
    '<h3>Player directory ' + badge('Sample records') + '</h3>' +
    '<label class="search-field">' + icon('search', 14) +
    '<input id="search" aria-label="Search players" placeholder="Name or server ID…" value="' +
    esc(search) + '"></label></div>' +
    '<div class="table-scroll"><table><thead><tr><th>Player</th><th>Server ID</th>' +
    '<th>Status</th><th>Detections</th><th>History</th></tr></thead><tbody>' +
    people.map((p) =>
      '<tr><td><button class="player-cell" data-player="' + p.id + '">' +
      '<span class="avatar">' + esc(p.name[0]) + '</span><b>' + esc(p.name) + '</b></button></td>' +
      '<td>#' + p.id + '</td>' +
      '<td>' + badge(banned.some((d) => d.playerId === p.id) ? 'Banned' : 'Seen in session',
                     banned.some((d) => d.playerId === p.id) ? 'danger' : 'neutral') + '</td>' +
      '<td>' + detections.filter((d) => d.playerId === p.id).length + '</td>' +
      '<td><button class="text-link" data-player="' + p.id + '">View player ' +
      icon('arrow-up-right', 13) + '</button></td></tr>').join('') +
    '</tbody></table>' +
    (people.length ? '' : empty('Try another name or choose an online server.')) +
    '</div></section>';
}

function sectionDetections() {
  return '<section class="panel">' + filterBar() +
    detectionTable(filterDetections(state.detections, server().id, search, category)) + '</section>';
}

function sectionBans() {
  const banned = serverDetections().filter((d) => d.action === 'Banned');
  return '<section class="panel"><div class="panel-heading"><h3>Ban history</h3>' +
    badge(bansOf().length + ' active') + '</div>' +
    (banned.length
      ? '<div class="table-scroll"><table><thead><tr><th>Player / ban ID</th><th>Reason</th>' +
        '<th>Status</th><th>Evidence</th><th>Action</th></tr></thead><tbody>' +
        banned.map((d) => {
          const revoked = state.revoked.includes(d.id);
          return '<tr><td><b>' + esc(d.player) + '</b><small class="mono">' + esc(d.id) + '</small></td>' +
            '<td>' + esc(d.kind) + '</td>' +
            '<td>' + badge(revoked ? 'Revoked' : 'Active', revoked ? 'neutral' : 'danger') + '</td>' +
            '<td><button class="text-link" data-investigate="' + d.id + '">Investigate ' +
            icon('arrow-up-right', 13) + '</button></td>' +
            '<td><button class="button small" data-revoke="' + d.id + '"' +
            (revoked ? ' disabled' : '') + '>Revoke ban</button></td></tr>';
        }).join('') + '</tbody></table></div>'
      : empty('This server has no ban records.')) + '</section>';
}

function sectionScreenshots() {
  const banned = serverDetections().filter((d) => d.action === 'Banned');
  return '<div class="notice">' + icon('image', 17) +
    ' Evidence previews are illustrative. No real player screenshots are included.</div>' +
    '<div class="evidence-grid">' + banned.map((d) =>
      '<button class="panel evidence-card" data-investigate="' + d.id + '">' +
      '<div class="evidence-preview">' + icon('scan-line', 35) +
      '<span>SIMULATED EVIDENCE</span><small>' + esc(d.id) + ' · ' + esc(d.time) + '</small></div>' +
      '<div><h3>' + esc(d.player) + ' ' + icon('arrow-up-right', 14) + '</h3>' +
      '<p>' + esc(d.kind) + ' · ' + d.confidence + '% confidence</p></div></button>').join('') +
    '</div>' + (banned.length ? '' : empty());
}

function sectionProtection() {
  const protections = protectionsOf();
  return '<div class="notice">' + icon('shield-check', 17) + '<span>' + enabledCount() + ' / ' +
    protections.length + ' modules enabled for ' + esc(server().name) +
    '. Click a module to configure enforcement.</span></div>' +
    ['Combat', 'Player', 'Server'].map((group) =>
      '<section class="panel protection-group"><div class="panel-heading">' +
      '<h3>' + group + ' protection</h3><span class="muted">' +
      protections.filter((p) => p.category === group && p.enabled).length + ' / 6 enabled</span></div>' +
      protections.filter((p) => p.category === group).map((p) =>
        '<div class="protection-row">' +
        '<button data-edit="' + esc(p.name) + '"><span class="protection-icon">' +
        icon('shield-check', 17) + '</span><span><b>' + esc(p.name) + '</b><small>' +
        esc(p.mode) + ' · ' + esc(p.action) + ' at ' + p.confidence + '% confidence</small></span></button>' +
        '<button class="icon-button" aria-label="Configure ' + esc(p.name) + '" data-edit="' +
        esc(p.name) + '">' + icon('sliders', 16) + '</button>' +
        toggle('Enable ' + p.name, p.enabled, 'data-protect="' + esc(p.name) + '"') +
        '</div>').join('') + '</section>').join('');
}

function sectionEvents() {
  return '<section class="panel"><div class="panel-heading"><h3>Protected events</h3>' +
    '<button class="button light small" data-add-event>' + icon('plus', 14) + ' Add event</button></div>' +
    '<div class="notice inline">' + icon('braces', 17) +
    ' Sample allowlist and rate limits. Changes do not reach a FiveM server.</div>' +
    '<div class="table-scroll"><table><thead><tr><th>Event / resource</th><th>Rate limit</th>' +
    '<th>Blocked</th><th>Enabled</th><th>Settings</th></tr></thead><tbody>' +
    (state.events[server().id] || []).map((e) =>
      '<tr><td><b class="mono">' + esc(e.name) + '</b><small>' + esc(e.resource) + '</small></td>' +
      '<td>' + e.rate + ' / minute</td><td>' + e.blocked + '</td>' +
      '<td>' + toggle('Protect ' + e.name, e.enabled, 'data-event-toggle="' + esc(e.id) + '"') + '</td>' +
      '<td><button class="icon-button" aria-label="Edit ' + esc(e.name) + '" data-event-edit="' +
      esc(e.id) + '">' + icon('sliders', 15) + '</button></td></tr>').join('') +
    '</tbody></table></div></section>';
}

function sectionLogs() {
  const activity = activityOf();
  return '<section class="panel"><div class="panel-heading"><h3>Activity &amp; audit trail</h3>' +
    '<div class="button-row"><button class="button small" data-stream>' +
    icon(state.stream ? 'pause' : 'play', 13) + ' ' + (state.stream ? 'Pause' : 'Resume') + '</button>' +
    '<button class="button small" data-export>' + icon('download', 13) + ' Export</button></div></div>' +
    '<div class="log-list">' + (activity.length
      ? activity.map((a) => '<div><span class="mono muted">' + esc(a.time) + '</span>' +
        badge('DEMO') + '<span>' + esc(a.text) + '</span></div>').join('')
      : empty()) + '</div></section>';
}

function sectionStaff() {
  const access = {
    Owner: 'Full access', Administrator: 'Manage servers & bans',
    Moderator: 'Review players & bans',
  };
  return '<section class="panel"><div class="panel-heading"><h3>Workspace members</h3>' +
    '<button class="button light small" data-invite>' + icon('plus', 14) +
    ' Add demo member</button></div>' +
    '<div class="table-scroll"><table><thead><tr><th>Member</th><th>Role</th><th>Access</th>' +
    '<th>Action</th></tr></thead><tbody>' + state.staff.map((s) =>
      '<tr><td>' + esc(s.email) + '</td><td>' + badge(s.role) + '</td>' +
      '<td>' + (access[s.role] || 'Read detections & evidence') + '</td>' +
      '<td>' + (s.role !== 'Owner'
        ? '<button class="text-link" data-remove-staff="' + esc(s.id) + '">Remove</button>'
        : icon('lock', 14)) + '</td></tr>').join('') +
    '</tbody></table></div>' +
    '<p class="panel-note">Sample membership only. No invitations or emails are sent.</p></section>';
}

function sectionIntegrations() {
  return '<div class="settings-grid">' +
    '<section class="panel settings-card"><span class="feature-icon">' + icon('plug', 25) + '</span>' +
    '<h3>Discord notifications</h3>' +
    '<p>Preview detection, ban, and server-status notification preferences.</p>' +
    '<div class="setting-row"><span>Demo notifications</span>' +
    toggle('Enable Discord demo notifications', state.integrationEnabled, 'data-integration') +
    '</div><button class="button" data-test-notification' +
    (state.integrationEnabled ? '' : ' disabled') + '>Preview test notification ' +
    icon('arrow-up-right', 14) + '</button></section>' +

    '<section class="panel settings-card"><span class="feature-icon">' + icon('terminal', 25) + '</span>' +
    '<h3>Server API</h3>' +
    '<p>Connect server heartbeats, detections, and configuration through a server-side integration.</p>' +
    badge('Not connected') +
    '<div class="code-token">NX_API_••••••••••••••••</div>' +
    '<a href="/docs" class="button">Read the connection guide ' + icon('arrow-up-right', 14) +
    '</a></section></div>';
}

function sectionLicense() {
  return '<section class="panel license-card"><div><span class="eyebrow">YOUR DEMO PLAN</span>' +
    '<h2>NexusAC Pro</h2><p>One workspace. All the tools to protect it.</p>' +
    badge('Sample license · not an activation key') + '</div>' +
    '<dl class="detail-list">' +
    '<div><dt>License</dt><dd class="mono">NX_DEMO_••••_2026</dd></div>' +
    '<div><dt>Server slots</dt><dd>' + state.servers.length + ' / 5</dd></div>' +
    '<div><dt>Billing</dt><dd>Demo · no charges</dd></div>' +
    '<div><dt>Protection modules</dt><dd>All included</dd></div></dl>' +
    '<a href="/register" class="button light">Create a real workspace ' +
    icon('arrow-up-right', 14) + '</a></section>';
}

function sectionSettings() {
  return '<section class="panel settings-card"><h3>Workspace preferences</h3>' +
    '<form class="form-stack" id="settings-form">' +
    '<label>Organization name<input name="organization" required maxlength="40" value="' +
    esc(state.organization) + '"></label>' +
    '<label class="checkbox-row"><input type="checkbox" name="notifications"' +
    (state.notifications ? ' checked' : '') + '> Enable dashboard notifications</label>' +
    '<p class="muted">Demo preferences reset when you reload the page. No personal account is ' +
    'connected.</p>' +
    '<button class="button light" type="submit">Save preferences ' + icon('check', 15) +
    '</button></form>' +
    '<div class="settings-reset"><div><h3>Start fresh</h3>' +
    '<p>Restore all sample servers, modules, and ban records.</p></div>' +
    '<button class="button" data-reset>' + icon('rotate', 14) + ' Reset demo</button></div></section>';
}

const SECTION_RENDERERS = {
  overview: sectionOverview, servers: sectionServers, players: sectionPlayers,
  detections: sectionDetections, bans: sectionBans, screenshots: sectionScreenshots,
  protection: sectionProtection, events: sectionEvents, logs: sectionLogs,
  staff: sectionStaff, integrations: sectionIntegrations, license: sectionLicense,
  settings: sectionSettings,
};

/* -------------------------------------------------------------------- render */

function render() {
  const s = server();
  const protections = protectionsOf();
  const enabled = enabledCount();

  document.getElementById('ws-name').innerHTML =
    esc(state.organization) + '<small>Demo workspace</small>';

  document.querySelectorAll('.sidebar-link[data-section]').forEach((link) => {
    link.classList.toggle('active', link.dataset.section === active);
    if (link.dataset.section === active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  const count = document.getElementById('count-detections');
  if (count) count.textContent = serverDetections().length || '';
  document.getElementById('crumb').textContent = SECTION_LABELS[active];

  const tone = !s.online ? 'neutral' : enabled === protections.length ? 'success' : 'warning';
  const label = !s.online ? 'Offline'
    : enabled === protections.length ? 'Protected' : 'Review protection';

  root.innerHTML =
    '<div class="server-toolbar">' +
    '<label class="server-select">' + icon('server', 16) +
    '<select aria-label="Select server" id="server-select">' + state.servers.map((v) =>
      '<option value="' + esc(v.id) + '"' + (v.id === s.id ? ' selected' : '') + '>' +
      esc(v.name) + '</option>').join('') + '</select></label>' +
    '<span class="badge ' + tone + '"><span class="status-dot"></span>' + label + '</span>' +
    '<span class="server-region">' + esc(s.region) + ' · ' +
      (s.online ? 'Online' : 'Last seen 2 hours ago') + '</span>' +
    '<span class="sync-note">' + icon('check-check', 13) +
      (s.online ? 'Configuration synced' : 'Waiting for connection') + '</span></div>' +

    '<div class="dashboard-title"><div><span class="eyebrow">' +
    (active === 'overview' ? 'COMMAND CENTER'
      : 'WORKSPACE / ' + SECTION_LABELS[active].toUpperCase()) + '</span>' +
    '<h2>' + (active === 'overview' ? 'Everything under control.' : SECTION_LABELS[active]) + '</h2>' +
    '<p>' + DESCRIPTIONS[active] + '</p></div>' +
    (active === 'overview'
      ? '<select aria-label="Chart time range" class="range-select" id="period">' +
        ['24 hours', '7 days'].map((p) =>
          '<option' + (p === period ? ' selected' : '') + '>' + p + '</option>').join('') + '</select>'
      : '') + '</div>' +

    SECTION_RENDERERS[active]();
}

/* ------------------------------------------------------------------- dialogs */

function dialog(title, body, onReady) {
  Modal.show(body, onReady, 'NEXUSAC / DEMO', title);
}

function investigate(id) {
  const d = state.detections.find((v) => v.id === id);
  if (!d) return;
  const revoked = state.revoked.includes(d.id);
  dialog('Detection investigation',
    '<div class="investigation-person"><span class="avatar large">' + esc(d.player[0]) + '</span>' +
    '<div><h3>' + esc(d.player) + '</h3><p>Player #' + d.playerId + ' · ' + esc(d.id) + '</p></div></div>' +
    '<div class="investigation-summary"><span class="eyebrow">' + esc(d.category) + '</span>' +
    '<h2>' + esc(d.kind) + '</h2><div><strong>' + d.confidence + '% <small>confidence</small></strong>' +
    badge(d.action, d.action === 'Banned' ? 'danger' : 'neutral') + '</div></div>' +
    '<h4>Evidence</h4><div class="evidence-preview">' + icon('scan-line', 35) +
    '<span>SIMULATED EVIDENCE</span><small>No real screenshot captured</small></div>' +
    '<dl class="detail-list">' +
    '<div><dt>Weapon</dt><dd class="mono">' + esc(d.weapon) + '</dd></div>' +
    '<div><dt>Distance</dt><dd>' + (d.distance ? d.distance + ' m' : 'Not applicable') + '</dd></div>' +
    '<div><dt>Resource</dt><dd>' + (d.category === 'Events' ? 'admin-tools' : 'Detection engine') +
    '</dd></div>' +
    '<div><dt>Recorded</dt><dd>' + esc(d.time) + ' · sample session</dd></div>' +
    '<div><dt>Ban status</dt><dd>' + (d.action !== 'Banned' ? 'No ban'
      : revoked ? 'Revoked' : 'Active') + '</dd></div></dl>' +
    '<h4>Sample identifiers</h4><div class="identifier-block">' +
    '<span>FiveM <code>demo:' + d.playerId + '</code></span>' +
    '<span>Discord <code>demo-discord-' + d.playerId + '</code></span>' +
    '<span>License <code>license:demo-' + d.playerId + '</code></span></div>' +
    '<div class="notice">' + icon('shield-check', 17) +
    ' A confidence score is a signal. Review evidence before enforcing a ban.</div>' +
    '<div class="button-row">' +
    '<button class="button light" data-player="' + d.playerId + '">View player ' +
    icon('arrow-up-right', 14) + '</button>' +
    (d.action === 'Banned' ? '<button class="button" data-go="bans">View ban ' +
      icon('arrow-right', 14) + '</button>' : '') + '</div>');
}

function playerProfile(id) {
  const numeric = Number(id);
  const detections = serverDetections().filter((d) => d.playerId === numeric);
  const named = detections[0] || { player: 'Player' };
  const known = [{ name: 'Kai', id: 24 }, { name: 'Luna', id: 58 }, { name: 'River', id: 84 }]
    .find((p) => p.id === numeric);
  const name = known ? known.name : named.player;
  dialog('Player profile',
    '<div class="investigation-person"><span class="avatar large">' + esc(name[0]) + '</span>' +
    '<div><h3>' + esc(name) + '</h3><p>Player #' + numeric + ' · ' + esc(server().name) + '</p></div></div>' +
    '<dl class="detail-list">' +
    '<div><dt>FiveM identifier</dt><dd>demo:' + numeric + '</dd></div>' +
    '<div><dt>Detections</dt><dd>' + detections.length + '</dd></div>' +
    '<div><dt>Active bans</dt><dd>' + bansOf().filter((d) => d.playerId === numeric).length +
    '</dd></div></dl>' +
    '<h4>Detection history</h4>' +
    (detections.length
      ? detections.map((d) => '<button class="history-item" data-investigate="' + d.id + '">' +
        '<span>' + esc(d.kind) + '<small>' + esc(d.id) + '</small></span>' +
        icon('arrow-up-right', 16) + '</button>').join('')
      : empty('No detection history for this sample player.')));
}

function editProtection(name) {
  const original = protectionsOf().find((p) => p.name === name);
  if (!original) return;
  const draft = { ...original };
  dialog(draft.name,
    '<form class="form-stack" id="protection-form">' +
    '<div class="setting-row"><span>Protection enabled</span>' +
    toggle('Protection enabled', draft.enabled, 'data-draft="enabled"') + '</div>' +
    '<label>Detection profile<select name="mode">' +
    ['Conservative', 'Balanced', 'Strict'].map((m) =>
      '<option' + (m === draft.mode ? ' selected' : '') + '>' + m + '</option>').join('') +
    '</select></label>' +
    '<fieldset><legend>Enforcement</legend><div class="segmented">' +
    ['Log', 'Kick', 'Ban'].map((a) =>
      '<button type="button" data-action="' + a + '" aria-pressed="' + (draft.action === a) + '"' +
      (draft.action === a ? ' class="active"' : '') + '>' + a + '</button>').join('') +
    '</div></fieldset>' +
    '<label>Minimum confidence <strong id="conf-label">' + draft.confidence + '%</strong>' +
    '<input type="range" min="50" max="100" name="confidence" value="' + draft.confidence + '"></label>' +
    '<div class="setting-row"><span>Evidence screenshot</span>' +
    toggle('Evidence screenshot', draft.screenshot, 'data-draft="screenshot"') + '</div>' +
    '<div class="setting-row"><span>Discord notification</span>' +
    toggle('Discord notification', draft.notification, 'data-draft="notification"') + '</div>' +
    '<div class="notice">Applies to ' + esc(server().name) + ' in this demo session.</div>' +
    '<button class="button light" type="submit">Save changes ' + icon('check', 15) + '</button></form>',
    (node) => {
      node.addEventListener('click', (event) => {
        const flag = event.target.closest('[data-draft]');
        if (flag) {
          const key = flag.dataset.draft;
          draft[key] = !draft[key];
          flag.classList.toggle('on', draft[key]);
          flag.setAttribute('aria-checked', String(draft[key]));
        }
        const act = event.target.closest('[data-action]');
        if (act) {
          draft.action = act.dataset.action;
          node.querySelectorAll('[data-action]').forEach((b) => {
            b.classList.toggle('active', b.dataset.action === draft.action);
            b.setAttribute('aria-pressed', String(b.dataset.action === draft.action));
          });
        }
      });
      node.addEventListener('input', (event) => {
        if (event.target.name === 'confidence') {
          draft.confidence = Number(event.target.value);
          node.querySelector('#conf-label').textContent = draft.confidence + '%';
        }
        if (event.target.name === 'mode') draft.mode = event.target.value;
      });
      node.querySelector('#protection-form').addEventListener('submit', (event) => {
        event.preventDefault();
        Modal.close();
        dispatch({ type: 'protection', serverId: server().id, protection: draft });
        toast('Demo configuration updated');
      });
    });
}

function editEvent(id) {
  const list = state.events[server().id] || [];
  const existing = id ? list.find((e) => e.id === id) : null;
  const draft = existing ? { ...existing }
    : { id: 'evt-' + Date.now(), name: '', resource: '', rate: 10, enabled: true, blocked: 0 };
  dialog(existing ? 'Edit protected event' : 'Add protected event',
    '<form class="form-stack" id="event-form">' +
    '<label>Event name<input name="name" required maxlength="100" placeholder="bank:transfer" value="' +
    esc(draft.name) + '"></label>' +
    '<label>Trusted resource<input name="resource" required maxlength="100" value="' +
    esc(draft.resource) + '"></label>' +
    '<label>Requests per minute<input type="number" name="rate" required min="1" max="1000" value="' +
    draft.rate + '"></label>' +
    '<div class="setting-row"><span>Protection enabled</span>' +
    toggle('Event protection enabled', draft.enabled, 'data-draft="enabled"') + '</div>' +
    '<button type="submit" class="button light">Save event ' + icon('check', 14) + '</button></form>',
    (node) => {
      node.addEventListener('click', (event) => {
        const flag = event.target.closest('[data-draft]');
        if (!flag) return;
        draft.enabled = !draft.enabled;
        flag.classList.toggle('on', draft.enabled);
        flag.setAttribute('aria-checked', String(draft.enabled));
      });
      node.querySelector('#event-form').addEventListener('submit', (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const name = form.name.value.trim();
        const resource = form.resource.value.trim();
        if (!name || !resource) return;
        if ((state.events[server().id] || []).some((v) => v.name === name && v.id !== draft.id)) {
          toast('This event already exists');
          return;
        }
        Modal.close();
        dispatch({ type: 'event', serverId: server().id,
                   event: { ...draft, name, resource, rate: Number(form.rate.value) } });
        toast('Demo event protection saved');
      });
    });
}

function inviteDialog() {
  dialog('Add demo member',
    '<form class="form-stack" id="invite-form">' +
    '<p>Explore workspace roles with sample membership. This does not grant real access.</p>' +
    '<label>Email<input type="email" name="email" required></label>' +
    '<label>Role<select name="role">' +
    ['Administrator', 'Moderator', 'Analyst', 'Viewer'].map((r) => '<option>' + r + '</option>').join('') +
    '</select></label>' +
    '<button class="button light" type="submit">Add demo member ' + icon('plus', 14) + '</button></form>',
    (node) => node.querySelector('#invite-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const email = event.currentTarget.email.value.trim();
      if (state.staff.some((s) => s.email.toLowerCase() === email.toLowerCase())) {
        toast('That member already exists');
        return;
      }
      Modal.close();
      dispatch({ type: 'staff', email, role: event.currentTarget.role.value });
      toast('Sample member added. No email sent.');
    }));
}

function confirmDialog(what) {
  const reset = what === 'reset';
  dialog(reset ? 'Reset the demo?' : 'Revoke this sample ban?',
    '<p>' + (reset
      ? 'This restores all sample data and removes changes made during this session.'
      : 'Ban ' + esc(what) + ' will be marked revoked. Its detection record and evidence will stay ' +
        'available.') + '</p>' +
    '<div class="button-row"><button class="button" data-cancel>Cancel</button>' +
    '<button class="button light" data-confirm>Confirm ' + (reset ? 'reset' : 'revocation') +
    '</button></div>',
    (node) => {
      node.querySelector('[data-cancel]').addEventListener('click', () => Modal.close());
      node.querySelector('[data-confirm]').addEventListener('click', () => {
        Modal.close();
        if (reset) {
          search = ''; category = 'All';
          dispatch({ type: 'reset' });
          toast('Demo reset');
        } else {
          dispatch({ type: 'revoke', id: what, time: new Date().toLocaleTimeString('en-GB') });
          toast('Sample ban revoked');
        }
      });
    });
}

function exportLogs() {
  const blob = new Blob([JSON.stringify(activityOf(), null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'nexusac-demo-' + server().id + '-logs.json';
  link.click();
  URL.revokeObjectURL(url);
  toast('Demo logs exported');
}

/* ------------------------------------------------------------------- events */

document.addEventListener('click', (event) => {
  const t = event.target;

  const nav = t.closest('.sidebar-link[data-section]');
  if (nav) {
    document.getElementById('sidebar').classList.remove('mobile-open');
    return navigate(nav.dataset.section);
  }
  if (t.closest('#menu')) return document.getElementById('sidebar').classList.toggle('mobile-open');
  if (t.closest('[data-go]')) return navigate(t.closest('[data-go]').dataset.go);
  if (t.closest('[data-stream]')) { dispatch({ type: 'stream' }); return; }
  if (t.closest('[data-export]')) return exportLogs();
  if (t.closest('[data-reset]') || t.closest('#reset-demo')) return confirmDialog('reset');
  if (t.closest('[data-invite]')) return inviteDialog();
  if (t.closest('[data-add-event]')) return editEvent(null);

  const investigateId = t.closest('[data-investigate]');
  if (investigateId) { Modal.close(); return investigate(investigateId.dataset.investigate); }

  const playerId = t.closest('[data-player]');
  if (playerId) { Modal.close(); return playerProfile(playerId.dataset.player); }

  const edit = t.closest('[data-edit]');
  if (edit) return editProtection(edit.dataset.edit);

  const eventEdit = t.closest('[data-event-edit]');
  if (eventEdit) return editEvent(eventEdit.dataset.eventEdit);

  const eventToggle = t.closest('[data-event-toggle]');
  if (eventToggle) {
    const found = (state.events[server().id] || []).find((e) => e.id === eventToggle.dataset.eventToggle);
    if (found) dispatch({ type: 'event', serverId: server().id,
                          event: { ...found, enabled: !found.enabled } });
    return;
  }

  const protect = t.closest('[data-protect]');
  if (protect) {
    const found = protectionsOf().find((p) => p.name === protect.dataset.protect);
    if (found) {
      dispatch({ type: 'protection', serverId: server().id,
                 protection: { ...found, enabled: !found.enabled } });
      toast(found.name + (found.enabled ? ' disabled' : ' enabled') + ' in demo');
    }
    return;
  }

  const revoke = t.closest('[data-revoke]');
  if (revoke && !revoke.disabled) return confirmDialog(revoke.dataset.revoke);

  const openServer = t.closest('[data-open-server]');
  if (openServer) {
    dispatch({ type: 'selectServer', id: openServer.dataset.openServer });
    return navigate('overview');
  }

  const cat = t.closest('[data-category]');
  if (cat) { category = cat.dataset.category; return render(); }

  if (t.closest('[data-integration]')) {
    dispatch({ type: 'integration', enabled: !state.integrationEnabled });
    toast('Demo notification preference updated');
    return;
  }
  if (t.closest('[data-test-notification]')) {
    return toast('Test notification preview: Silent Aim · Marcus · 96% confidence. ' +
                 'No webhook was called.');
  }

  const removeStaff = t.closest('[data-remove-staff]');
  if (removeStaff) {
    dispatch({ type: 'removeStaff', id: removeStaff.dataset.removeStaff });
    toast('Demo member removed');
  }
});

document.addEventListener('change', (event) => {
  if (event.target.id === 'server-select') {
    search = ''; category = 'All';
    return dispatch({ type: 'selectServer', id: event.target.value });
  }
  if (event.target.id === 'period') { period = event.target.value; return render(); }
});

/* Search must not lose focus or caret on every keystroke, so the table body is
   replaced in place rather than the whole view being re-rendered. */
document.addEventListener('input', (event) => {
  if (event.target.id !== 'search') return;
  search = event.target.value;
  const panel = event.target.closest('.panel');
  const scroll = panel && panel.querySelector('.table-scroll');
  if (!scroll) return render();
  const fresh = document.createElement('div');
  fresh.innerHTML = active === 'players' ? sectionPlayers() : sectionDetections();
  const replacement = fresh.querySelector('.table-scroll');
  if (replacement) scroll.replaceWith(replacement);
});

document.addEventListener('submit', (event) => {
  if (event.target.id !== 'settings-form') return;
  event.preventDefault();
  const data = new FormData(event.target);
  dispatch({
    type: 'settings',
    organization: String(data.get('organization') || '').trim() || 'Demo workspace',
    notifications: data.get('notifications') === 'on',
  });
  toast('Workspace preferences saved for this session');
});

/* --------------------------------------------------------------------- boot */

active = SECTIONS.includes(window.DEMO_SECTION) ? window.DEMO_SECTION : 'overview';
render();
setInterval(() => {
  // busy() covers an open drawer and a focused field. Without it the simulated
  // tick repaints the whole view every 5 seconds and throws away whatever was
  // half-typed into the search box, or shuts a dropdown mid-choice.
  if (!state.stream || busy()) return;
  dispatch({ type: 'tick', time: new Date().toLocaleTimeString('en-GB') });
}, 5000);
