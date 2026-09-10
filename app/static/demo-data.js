/* The demo's simulated dataset and reducer, ported from the Next.js build's
   lib/demo.ts. Nothing here touches a real server: it is sample data that lives
   in the page for the length of the session. */

const SECTIONS = ['overview', 'servers', 'players', 'detections', 'bans', 'screenshots',
                  'protection', 'events', 'logs', 'staff', 'integrations', 'license', 'settings'];

const SECTION_LABELS = {
  overview: 'Overview', servers: 'Servers', players: 'Players', detections: 'Detections',
  bans: 'Bans', screenshots: 'Screenshots', protection: 'Protection Center',
  events: 'Event Protection', logs: 'Logs', staff: 'Staff', integrations: 'Integrations',
  license: 'License', settings: 'Settings',
};

const SECTION_ICONS = {
  overview: 'grid', servers: 'server', players: 'users', detections: 'scan-line',
  bans: 'ban', screenshots: 'image', protection: 'shield-check', events: 'braces',
  logs: 'log', staff: 'users', integrations: 'plug', license: 'key', settings: 'settings',
};

const DESCRIPTIONS = {
  overview: 'A live view of your community’s security.',
  servers: 'Your connected servers, health, and configuration.',
  players: 'Know who’s connected. Understand their history.',
  detections: 'Every signal, with the context to act.',
  bans: 'Review enforcement and linked evidence.',
  screenshots: 'Evidence linked directly to detection records.',
  protection: 'Fine-tune your protection, one module at a time.',
  events: 'Keep sensitive server events under your control.',
  logs: 'A clear timeline of server and staff activity.',
  staff: 'The right access, for the right people.',
  integrations: 'Connect your security workflow.',
  license: 'Your plan, server slots, and activation status.',
  settings: 'Make this workspace your own.',
};

const MODULES = {
  Combat: ['Anti Aimbot', 'Anti Silent Aim', 'Anti Triggerbot', 'Anti Magic Bullet',
           'Anti Damage Modifier', 'Anti Rapid Fire'],
  Player: ['Anti Godmode', 'Anti Invisible', 'Anti Armor Abuse', 'Anti Self Revive',
           'Anti Super Jump', 'Anti Noclip'],
  Server: ['Injection Protection', 'Event Firewall', 'Entity Protection',
           'Explosion Protection', 'Weapon Protection', 'Resource Protection'],
};

function makeProtections() {
  const out = [];
  for (const [category, names] of Object.entries(MODULES)) {
    for (const name of names) {
      out.push({ name, category, enabled: true, mode: 'Balanced', action: 'Ban',
                 confidence: 85, screenshot: true, notification: true });
    }
  }
  return out;
}

const INITIAL_DETECTIONS = [
  { id: 'NX-428901', serverId: 'no-limits', player: 'Marcus', playerId: 182, kind: 'Silent Aim', category: 'Combat', confidence: 96, action: 'Banned', time: '18:42:08', weapon: 'WEAPON_CARBINERIFLE', distance: 143.2 },
  { id: 'NX-428900', serverId: 'no-limits', player: 'Unknown', playerId: 491, kind: 'Event Abuse', category: 'Events', confidence: 91, action: 'Blocked', time: '18:38:22', weapon: '—', distance: 0 },
  { id: 'NX-428899', serverId: 'no-limits', player: 'James', playerId: 102, kind: 'Executor Injection', category: 'Injection', confidence: 99, action: 'Banned', time: '18:31:17', weapon: '—', distance: 0 },
  { id: 'NX-428898', serverId: 'no-limits', player: 'Alex', playerId: 73, kind: 'Triggerbot', category: 'Combat', confidence: 93, action: 'Banned', time: '18:25:03', weapon: 'WEAPON_PISTOL', distance: 38.6 },
  { id: 'NX-428897', serverId: 'no-limits', player: 'Ghost', playerId: 219, kind: 'Entity Spam', category: 'Entities', confidence: 89, action: 'Blocked', time: '18:21:46', weapon: '—', distance: 0 },
  { id: 'NX-428896', serverId: 'no-limits', player: 'River', playerId: 84, kind: 'Damage Modifier', category: 'Weapons', confidence: 87, action: 'Flagged', time: '18:16:12', weapon: 'WEAPON_PISTOL', distance: 52.4 },
  { id: 'NX-428895', serverId: 'no-limits', player: 'Blake', playerId: 97, kind: 'Silent Aim', category: 'Combat', confidence: 97, action: 'Banned', time: '17:48:51', weapon: 'WEAPON_CARBINERIFLE', distance: 111 },
  { id: 'NX-428894', serverId: 'no-limits', player: 'Nova', playerId: 115, kind: 'Executor Injection', category: 'Injection', confidence: 99, action: 'Banned', time: '17:36:03', weapon: '—', distance: 0 },
  { id: 'NX-428893', serverId: 'no-limits', player: 'Zed', playerId: 162, kind: 'Triggerbot', category: 'Combat', confidence: 98, action: 'Banned', time: '17:12:09', weapon: 'WEAPON_PISTOL', distance: 44 },
  { id: 'NX-428880', serverId: 'sandbox', player: 'TestPlayer', playerId: 1, kind: 'Event Abuse', category: 'Events', confidence: 92, action: 'Blocked', time: '18:20:00', weapon: '—', distance: 0 },
];

const SERVER_IDS = ['no-limits', 'sandbox', 'staging'];

function makeEvents(id) {
  return [
    { id: 'evt-1', name: 'admin:revive', resource: 'admin-tools', rate: 5, enabled: true, blocked: id === 'no-limits' ? 241 : 4 },
    { id: 'evt-2', name: 'bank:transfer', resource: 'qb-banking', rate: 10, enabled: true, blocked: id === 'no-limits' ? 156 : 2 },
    { id: 'evt-3', name: 'inventory:addItem', resource: 'ox_inventory', rate: 20, enabled: true, blocked: id === 'no-limits' ? 84 : 11 },
  ];
}

function createDemoState() {
  const protections = {}, events = {};
  for (const id of SERVER_IDS) { protections[id] = makeProtections(); events[id] = makeEvents(id); }
  return {
    servers: [
      { id: 'no-limits', name: 'No Limits RP', region: 'US East', players: 128, capacity: 200, online: true, uptime: '99.99%', latency: 24, blocked: 481 },
      { id: 'sandbox', name: 'Development Server', region: 'EU West', players: 4, capacity: 32, online: true, uptime: '99.95%', latency: 38, blocked: 17 },
      { id: 'staging', name: 'Staging Server', region: 'US East', players: 0, capacity: 32, online: false, uptime: '—', latency: 0, blocked: 0 },
    ],
    selectedServer: 'no-limits',
    detections: INITIAL_DETECTIONS.map((d) => ({ ...d })),
    protections,
    events,
    revoked: [],
    activity: [
      { id: 'a1', text: 'Silent Aim detected · Marcus', time: '18:42:08', serverId: 'no-limits' },
      { id: 'a2', text: 'Evidence linked to NX-428901', time: '18:42:09', serverId: 'no-limits' },
      { id: 'a3', text: 'Configuration synced · version 24', time: '18:40:01', serverId: 'no-limits' },
    ],
    staff: [
      { id: 'owner', email: 'kai@example.test', role: 'Owner' },
      { id: 'admin', email: 'admin@example.test', role: 'Administrator' },
      { id: 'analyst', email: 'analyst@example.test', role: 'Analyst' },
    ],
    notifications: true,
    organization: 'Kai’s organization',
    stream: true,
    tick: 0,
    integrationEnabled: false,
  };
}

const TICK_MESSAGES = [
  'Heartbeat received · configuration synced',
  'Player connection verified',
  'Event firewall checked protected resources',
  'Evidence index synchronized',
  'Detection engine health check passed',
];

/* Mutates and returns state. The React version was a pure reducer; here the
   caller re-renders after every dispatch, so in-place mutation is equivalent
   and avoids cloning the whole tree on each simulated tick. */
function demoReduce(state, action) {
  switch (action.type) {
    case 'reset':
      return createDemoState();

    case 'selectServer':
      if (state.servers.some((s) => s.id === action.id)) state.selectedServer = action.id;
      return state;

    case 'protection': {
      const list = state.protections[action.serverId];
      if (!list || !list.some((p) => p.name === action.protection.name)) return state;
      state.protections[action.serverId] = list.map((p) =>
        p.name === action.protection.name
          ? { ...action.protection,
              confidence: Math.min(100, Math.max(50, action.protection.confidence)) }
          : p);
      state.activity.unshift({
        id: 'config-' + state.tick + '-' + state.activity.length,
        text: action.protection.name + ' configuration updated',
        time: 'Just now', serverId: action.serverId,
      });
      state.activity = state.activity.slice(0, 60);
      return state;
    }

    case 'stream':
      state.stream = !state.stream;
      return state;

    case 'tick': {
      if (!state.stream) return state;
      state.tick += 1;
      const server = state.servers.find((s) => s.id === state.selectedServer);
      if (!server || !server.online) return state;
      state.activity.unshift({
        id: 'live-' + state.tick,
        text: TICK_MESSAGES[state.tick % TICK_MESSAGES.length],
        time: action.time, serverId: server.id,
      });
      state.activity = state.activity.slice(0, 60);
      return state;
    }

    case 'revoke': {
      const target = state.detections.find((d) => d.id === action.id && d.action === 'Banned');
      if (!target || state.revoked.includes(action.id)) return state;
      state.revoked.push(action.id);
      state.activity.unshift({
        id: 'revoke-' + action.id,
        text: 'Ban ' + action.id + ' revoked in demo',
        time: action.time, serverId: target.serverId,
      });
      state.activity = state.activity.slice(0, 60);
      return state;
    }

    case 'event': {
      const list = state.events[action.serverId];
      if (!list) return state;
      state.events[action.serverId] = list.some((e) => e.id === action.event.id)
        ? list.map((e) => (e.id === action.event.id ? action.event : e))
        : [...list, action.event];
      return state;
    }

    case 'staff':
      if (state.staff.some((s) => s.email.toLowerCase() === action.email.toLowerCase())) return state;
      state.staff.push({ id: action.email, email: action.email, role: action.role });
      return state;

    case 'removeStaff':
      state.staff = state.staff.filter((s) => s.id !== action.id || s.role === 'Owner');
      return state;

    case 'settings':
      state.organization = action.organization;
      state.notifications = action.notifications;
      return state;

    case 'integration':
      state.integrationEnabled = action.enabled;
      return state;

    default:
      return state;
  }
}

function filterDetections(detections, serverId, search, category) {
  const needle = search.toLowerCase();
  return detections.filter((d) =>
    d.serverId === serverId &&
    (category === 'All' || d.category === category) &&
    (d.player + ' ' + d.playerId + ' ' + d.kind + ' ' + d.id).toLowerCase().includes(needle));
}
