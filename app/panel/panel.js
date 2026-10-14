/* NexusAC in-game staff panel -- 2026-10-09 rebuild.
   Every page asks the server for one section (post 'section'); every change is
   one command (post 'exec') that the server runs as this admin after checking
   their capabilities. Nothing is trusted here: hiding a button is convenience,
   the server is the gate. The protocol is unchanged from the previous panel. */
'use strict';

const RES = typeof GetParentResourceName === 'function' ? GetParentResourceName() : 'NexusAC';
function post(name, body) {
  return fetch('https://' + RES + '/' + name, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=UTF-8' },
    body: JSON.stringify(body || {}),
  }).catch(() => null);
}

/* ------------------------------------------------------------------ state */
const S = {
  open: false, info: {}, caps: {}, tab: 'dashboard', data: {}, filters: {}, drafts: {},
  drawer: null, modal: null, pendingRender: false, settingsGroup: null, playerSrc: null,
  evidenceId: null, protId: null, detId: null, invId: null, serialId: null,
  nexFrames: {}, lookup: null, navOpen: {}, protTab: 'detections', protCat: '',
  spLayout: 3, spFilter: 'all', banView: 'card', banStatus: 'all', detSev: 'all', staffOnly: false,
  auditKind: 'all', items: {}, objNet: 'all', objRes: 'all', objKind: 'all',
};
try { const saved = JSON.parse(localStorage.getItem('nx-ui') || '{}'); Object.assign(S.navOpen, saved.navOpen || {}); if (saved.spLayout) S.spLayout = saved.spLayout; if (saved.banView) S.banView = saved.banView; } catch (e) { /* storage unavailable */ }
function savePrefs() { try { localStorage.setItem('nx-ui', JSON.stringify({ navOpen: S.navOpen, spLayout: S.spLayout, banView: S.banView })); } catch (e) { /* ignore */ } }

/* ------------------------------------------------------------------ icons */
const ICONS = {
  dash: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  radar: '<path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 6a6 6 0 1 0 6 6"/><path d="M12 12l7-7"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="M4.9 4.9l14.2 14.2"/>',
  out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
  warn: '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  folder: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  layers: '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>',
  audit: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  box: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.3 7L12 12l8.7-5M12 22V12"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  bolt: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  term: '<path d="M4 17l6-6-6-6M12 19h8"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  chev: '<path d="M9 18l6-6-6-6"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  refresh: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/>',
  power: '<path d="M18.4 6.6a9 9 0 1 1-12.8 0M12 2v10"/>',
  move: '<path d="M5 9l-3 3 3 3M9 5l3-3 3 3M15 19l-3 3-3-3M19 9l3 3-3 3M2 12h20M12 2v20"/>',
  cross: '<circle cx="12" cy="12" r="10"/><path d="M22 12h-4M6 12H2M12 6V2M12 22v-4"/>',
  g1: '<rect x="4" y="4" width="16" height="16" rx="2"/>',
  g2: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18M3 12h18"/>',
  g3: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  mem: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01"/>',
  tag: '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><path d="M7 7h.01"/>',
  bag: '<path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18M16 10a4 4 0 0 1-8 0"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><circle cx="11.5" cy="14.5" r="2.5"/><path d="M13.3 16.3L15 18"/>',
  bars: '<path d="M2 20h.01M7 20v-4M12 20v-8M17 20V8M22 4v16"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  car: '<path d="M5 17h14M6 17v2M18 17v2M3 13l2-6h14l2 6v4H3z"/><circle cx="7.5" cy="14" r=".5"/><circle cx="16.5" cy="14" r=".5"/>',
  cpu: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
};
function I(name, cls) { return '<svg class="i' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24">' + (ICONS[name] || '') + '</svg>'; }

/* ------------------------------------------------------------------ navigation model */
const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: 'dash', section: 'overview', cap: 'view', poll: 5000 },
  { id: 'players', label: 'Players', icon: 'users', section: 'players', cap: 'view_players', poll: 3000 },
  { id: 'spectate', label: 'Spectate', icon: 'eye', section: 'nex', cap: 'stream', poll: 2000, also: ['players', 'overview'] },
  { id: 'detections', label: 'Detections', icon: 'radar', section: 'feed', cap: 'view', poll: 2500 },
  { id: 'bans', label: 'Bans', icon: 'ban', section: 'bans', cap: 'view', poll: 0 },
  { id: 'kicks', label: 'Kicks', icon: 'out', section: 'punishments', cap: 'view', poll: 0 },
  { id: 'warns', label: 'Warns', icon: 'warn', section: 'punishments', cap: 'view', poll: 0 },
  { group: 'investigation', label: 'Investigation', icon: 'folder', items: [
    { id: 'evidence', label: 'Evidence', icon: 'file', section: 'evidence', cap: 'view_evidence', poll: 8000 },
    { id: 'inventories', label: 'Inventories', icon: 'bag', section: 'inventories', cap: 'view_players', poll: 0 },
    { id: 'logs', label: 'Logs', icon: 'term', section: 'logs', cap: 'view', poll: 5000 },
    { id: 'objects', label: 'Object Log', icon: 'box', section: 'objects', cap: 'view', poll: 1500, isNew: true },
  ] },
  { group: 'management', label: 'Management', icon: 'layers', items: [
    { id: 'protection', label: 'Configuration', icon: 'shield', section: 'protections', cap: 'view', poll: 6000, also: ['config'], isNew: true },
    { id: 'whitelist', label: 'Admin Whitelist', icon: 'users', section: 'whitelist', cap: 'view', poll: 0, isNew: true },
    { id: 'resources', label: 'Resources', icon: 'box', section: 'resources', cap: 'view', poll: 0 },
    { id: 'webhooks', label: 'Webhooks', icon: 'link', section: 'webhooks', cap: 'config', poll: 0 },
    { id: 'events', label: 'Event Protection', icon: 'bolt', section: 'eventRules', cap: 'view', poll: 0 },
    { id: 'entities', label: 'Entity Rules', icon: 'car', section: 'config', cap: 'entity_rules', poll: 0 },
    { id: 'cleanup', label: 'Cleanup', icon: 'trash', section: 'cleanup', cap: 'config', poll: 0 },
    { id: 'security', label: 'Security', icon: 'lock', section: 'security', cap: 'config', poll: 0 },
    { id: 'performance', label: 'Performance', icon: 'cpu', section: 'profile', cap: 'config', poll: 3000 },
  ] },
  { id: 'audit', label: 'Audit Log', icon: 'audit', section: 'punishments', cap: 'view', poll: 0 },
];
const TABS = [];
NAV.forEach((n) => { if (n.items) n.items.forEach((t) => { t.parent = n.group; TABS.push(t); }); else TABS.push(n); });

/* ------------------------------------------------------------------ helpers */
const $ = (id) => document.getElementById(id);
function h(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function num(v, digits) {
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return digits != null ? n.toFixed(digits) : (Math.abs(n) >= 1000 ? n.toLocaleString('en-US') : String(Math.round(n * 100) / 100));
}
function secs(at) { let t = Number(at); if (!isFinite(t) || t <= 0) return null; if (t > 1e12) t = t / 1000; return t; }
function when(at) {
  const t = secs(at);
  if (!t) return '-';
  const d = new Date(t * 1000);
  const p = (x) => String(x).padStart(2, '0');
  return p(d.getMonth() + 1) + '/' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}
function ago(at) {
  const t = secs(at);
  if (!t) return '-';
  const s = Math.max(0, Math.floor(Date.now() / 1000 - t));
  if (s < 10) return 'a few seconds ago';
  if (s < 60) return s + ' seconds ago';
  if (s < 3600) { const m = Math.floor(s / 60); return m + (m === 1 ? ' minute ago' : ' minutes ago'); }
  if (s < 86400) { const hh = Math.floor(s / 3600); return hh + (hh === 1 ? ' hour ago' : ' hours ago'); }
  const d = Math.floor(s / 86400); return d + (d === 1 ? ' day ago' : ' days ago');
}
function dur(sec) {
  const s = Math.floor(Number(sec) || 0);
  const d = Math.floor(s / 86400), hh = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return (d ? d + 'd ' : '') + (hh ? hh + 'h ' : '') + m + 'm';
}
function arr(v) { return Array.isArray(v) ? v : (v && typeof v === 'object' ? Object.values(v) : []); }
function can(cap) { return S.caps[cap] === true; }
function tabOf(id) { return TABS.find((t) => t.id === id); }
function filterRows(rows, q, fields) {
  q = (q || '').trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => fields.some((f) => String(typeof f === 'function' ? f(r) : r[f] == null ? '' : r[f]).toLowerCase().includes(q)));
}
function empty(t, text) { return '<div class="empty"><b>' + h(t) + '</b>' + h(text || '') + '</div>'; }
function table(heads, rows, emptyHtml, widths) {
  if (!rows.length) return emptyHtml || empty('Nothing here yet', '');
  const cols = widths ? '<colgroup>' + widths.map((w) => '<col style="width:' + w + '">').join('') + '</colgroup>' : '';
  return '<div class="table-wrap"><table class="t">' + cols + '<thead><tr>' +
    heads.map((x) => { const right = x.charAt(0) === '>'; return '<th' + (right ? ' class="right"' : '') + '>' + h(right ? x.slice(1) : x) + '</th>'; }).join('') +
    '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
}
function badge(text, kind) { return '<span class="badge ' + (kind || '') + '">' + h(text) + '</span>'; }
function head(t, count, tools, sub) {
  return '<div class="page-head"><div class="pill-title">' + (count != null ? 'Found <em>' + h(count) + '</em> ' : '') + h(t) + '</div><span class="spacer"></span>' + (tools || '') + '</div>' +
    (sub ? '<div class="page-sub">' + h(sub) + '</div>' : '');
}
function search(key, placeholder) {
  return '<div class="search-wrap">' + I('search', 'sm') + '<input class="input search" id="search-' + key + '" data-filter="' + key + '" placeholder="' + h(placeholder || 'Search...') +
    '" value="' + h(S.filters[key] || '') + '"></div>';
}
function sel(attr, opts, cur, width) {
  return '<select class="select" ' + attr + (width ? ' style="width:' + width + '"' : '') + '>' +
    opts.map((o) => { const v = Array.isArray(o) ? o[0] : o, l = Array.isArray(o) ? o[1] : o; return '<option value="' + h(v) + '"' + (String(v) === String(cur) ? ' selected' : '') + '>' + h(l) + '</option>'; }).join('') + '</select>';
}
function loading(t) { return (t ? head(t) : '') + '<div class="card">' + empty('Loading', 'Asking the server...') + '</div>'; }
function kv(pairs) {
  return '<dl class="kv">' + pairs.filter((p) => p && p[1] !== undefined && p[1] !== null && p[1] !== '')
    .map(([k, v, raw]) => '<dt>' + h(k) + '</dt><dd>' + (raw ? v : h(v)) + '</dd>').join('') + '</dl>';
}
function scalars(obj, skip) {
  const out = [];
  Object.keys(obj || {}).sort().forEach((k) => {
    if (skip && skip.includes(k)) return;
    const v = obj[k];
    if (v === null || v === undefined || typeof v === 'object') return;
    out.push([k, typeof v === 'boolean' ? (v ? 'yes' : 'no') : v]);
  });
  return out;
}
function pretty(v) { try { return JSON.stringify(v, null, 2); } catch (e) { return String(v); } }
function pingCls(p) { p = Number(p) || 0; return p < 60 ? 'ping good' : (p < 150 ? 'ping' : 'ping bad'); }
function riskCls(r) { r = Number(r) || 0; return r >= 60 ? 'risk hot' : (r > 0 ? 'risk warm' : 'risk cool'); }
function initialsOf(name) { const t = String(name || '?').trim(); return (t[0] || '?').toUpperCase(); }

/* ------------------------------------------------------------------ server I/O */
let reqSeq = 0;
function request(section, arg) { reqSeq += 1; post('section', { section, arg, request: reqSeq }); }
function exec(cmd) { post('exec', cmd); }
function refreshTab(force) {
  const t = tabOf(S.tab);
  if (!t) return;
  if (t.id === 'evidence') request('evidence', S.filters.evidence || '');
  else if (t.id === 'inventories') request('inventories', S.filters.inventories || '');
  else if (t.id === 'logs') request('logs', {});
  else request(t.section);
  (t.also || []).forEach((sec) => request(sec));
  if (force && S.drawer === 'player' && S.playerSrc) request('player', S.playerSrc);
}

/* ------------------------------------------------------------------ toasts / modal / drawer */
function toast(ok, msg) {
  const box = $('toasts');
  const el = document.createElement('div');
  el.className = 'toast' + (ok ? '' : ' bad');
  el.innerHTML = '<b>' + (ok ? 'Done' : 'Refused') + '</b>' + h(msg || '');
  box.appendChild(el);
  while (box.children.length > 4) box.removeChild(box.firstChild);
  setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, ok ? 3500 : 6000);
}
function modal(html, onReady) {
  S.modal = true;
  $('modal').innerHTML = html;
  $('modal-shade').classList.remove('hidden');
  if (onReady) onReady($('modal'));
  const first = $('modal').querySelector('input, textarea, select');
  if (first) first.focus();
}
function closeModal() {
  S.modal = null;
  $('modal').classList.remove('wide');
  $('modal-shade').classList.add('hidden');
  $('modal').innerHTML = '';
}
/* A confirm with an optional reason. The server requires 3-200 characters for
   every punishment; checked here too so the admin is told before sending. */
function confirmAction(opts) {
  const reason = opts.reason !== false;
  modal('<h2>' + h(opts.title) + '</h2><p>' + h(opts.text || '') + '</p>' + (opts.extra || '') +
    (reason ? '<label class="field"><span>Reason (shown to the player)</span><input class="input" id="m-reason" maxlength="200" placeholder="Why is this happening?"></label>' : '') +
    '<div id="m-error" class="muted" style="margin-top:8px"></div>' +
    '<div class="foot"><button class="btn" data-m="cancel">Cancel</button><button class="btn ' + (opts.danger ? 'danger' : 'primary') + '" data-m="ok">' + h(opts.ok || 'Confirm') + '</button></div>',
  (node) => {
    node.querySelector('[data-m=cancel]').onclick = closeModal;
    const go = () => {
      const r = reason ? node.querySelector('#m-reason').value.trim() : '';
      if (reason && (r.length < 3 || r.length > 200)) { node.querySelector('#m-error').textContent = 'A reason of 3 to 200 characters is required.'; return; }
      const values = {};
      node.querySelectorAll('[data-mv]').forEach((el) => { values[el.getAttribute('data-mv')] = el.value; });
      closeModal();
      opts.onOk(r, values);
    };
    node.querySelector('[data-m=ok]').onclick = go;
    node.querySelectorAll('input').forEach((el) => el.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); }));
  });
}
function openDrawer(kind) { S.drawer = kind; $('drawer').classList.toggle('wide', kind === 'inv' || kind === 'banshots'); renderDrawer(); }
function closeDrawer() {
  S.drawer = null; S.evidenceId = null; S.protId = null; S.invId = null; S.serialId = null; S.detId = null; S.banShotId = null;
  if (S.tab !== 'spectate') S.playerSrc = null;
  $('drawer').classList.add('hidden');
  $('drawer').innerHTML = '';
}
function drawerShell(t, body, extraHead) {
  return '<div class="drawer-head"><h2>' + h(t) + '</h2>' + (extraHead || '') + '<button class="icon-btn" data-act="drawer-close" title="Close">' + I('x', 'sm') + '</button></div>' +
    '<div class="drawer-body">' + body + '</div>';
}

/* ------------------------------------------------------------------ nav */
function navCount(id) {
  if (id === 'players' && S.data.players) return { n: arr(S.data.players).length };
  if (id === 'detections' && S.data.feed) {
    const n = arr(S.data.feed).filter((r) => secs(r.at) && Date.now() / 1000 - secs(r.at) < 3600 && r.stream !== 'entity').length;
    return n ? { n, red: true } : null;
  }
  return null;
}
function navItem(t, sub) {
  if (!can(t.cap)) return '';
  const c = navCount(t.id);
  return '<button class="nav-item' + (S.tab === t.id ? ' active' : '') + '" data-tab="' + t.id + '">' + I(t.icon) + '<span class="label">' + h(t.label) + '</span>' +
    (c ? '<span class="count' + (c.red ? ' red' : '') + '">' + c.n + '</span>' : '') + (t.isNew ? '<span class="tag-new">New</span>' : '') + '</button>';
}
function renderNav() {
  let html = '';
  let afterGroup = null;   // null = start, true = right after a section
  NAV.forEach((n) => {
    if (!n.items) {
      const item = navItem(n);
      if (item && afterGroup !== false) { html += '<div class="nav-head">' + (afterGroup ? 'Records' : 'Live') + '</div>'; afterGroup = false; }
      html += item;
      return;
    }
    afterGroup = true;
    const kids = n.items.map((t) => navItem(t, true)).join('');
    if (!kids) return;
    // 2026-10-14 Aurora: sections are always open, under a heading.
    html += '<div class="nav-head">' + h(n.label) + '</div>' + kids;
  });
  $('nav').innerHTML = html;
}
function setTab(id) {
  const t = tabOf(id);
  if (!t || !can(t.cap)) return;
  S.tab = id;
  closeDrawer();
  $('content').scrollTop = 0;
  renderNav();
  render(true);
  refreshTab();
}

/* ------------------------------------------------------------------ rendering */
function isTyping() {
  const a = document.activeElement;
  if (!a) return false;
  const inside = $('content').contains(a) || $('drawer').contains(a);
  // 2026-10-11: a focused dropdown counts too -- rebuilding the page closed it
  // mid-choice (Signal actions, Protection actions).
  return inside && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT') && !a.hasAttribute('data-filter');
}
function render(force) {
  if (!S.open) return;
  if (!force && (isTyping() || mouseDown)) { S.pendingRender = true; return; }
  S.pendingRender = false;
  const focusId = document.activeElement && document.activeElement.id;
  const caret = focusId && document.activeElement.selectionStart;
  const scroll = $('content').scrollTop;
  let html;
  try { html = (PAGES[S.tab] || (() => empty('Unknown page', '')))(); }
  catch (e) { html = '<div class="card">' + empty('This page could not be drawn', String(e && e.message || e)) + '</div>'; }
  // Live screens keep their <img> across re-renders (the Spectate page polls
  // every 2 s): a rebuilt tile would decode its frame again and blink.
  const liveImgs = {};
  $('content').querySelectorAll('img[id^="nex-img-"]').forEach((i) => { if (!i.classList.contains('hidden') && i.src) liveImgs[i.id] = i; });
  // 2026-10-11: nothing changed on this page = no DOM rebuild (polls used to
  // rebuild hundreds of rows every few seconds for nothing).
  const renderKey = S.tab + '|' + (S.protTab || '');
  if (!force && S.lastRenderKey === renderKey && S.lastRenderHtml === html) {
    if (S.drawer) renderDrawer();
    return;
  }
  S.lastRenderKey = renderKey;
  S.lastRenderHtml = html;
  $('content').innerHTML = html;
  for (const id in liveImgs) {
    const fresh = $(id);
    if (!fresh) continue;
    fresh.replaceWith(liveImgs[id]);
    const wait = $(id.replace('nex-img-', 'nex-wait-'));
    if (wait) wait.parentNode.removeChild(wait);
  }
  $('content').scrollTop = scroll;
  if (focusId) {
    const el = $(focusId);
    if (el) { el.focus(); try { if (caret != null) el.setSelectionRange(caret, caret); } catch (e) { /* not text */ } }
  }
  if (S.drawer) renderDrawer();
}
function renderDrawer() {
  const box = $('drawer');
  if (!S.drawer) { box.classList.add('hidden'); return; }
  if (box.contains(document.activeElement) && isTyping()) { S.pendingRender = true; return; }
  let html = '';
  try { html = (DRAWERS[S.drawer] || (() => ''))(); }
  catch (e) { html = drawerShell('Error', empty('Could not draw this', String(e && e.message || e))); }
  const body = box.querySelector('.drawer-body');
  const scroll = body ? body.scrollTop : 0;
  box.innerHTML = html;
  box.classList.remove('hidden');
  const nb = box.querySelector('.drawer-body');
  if (nb) nb.scrollTop = scroll;
}
function renderChrome() {
  const o = S.data.overview || {};
  const online = o.online != null ? o.online : arr(S.data.players).length;
  $('server-slots').textContent = num(online) + '/' + num(o.maxSlots || S.info.maxSlots || 0);
  const mode = o.mode || S.info.mode;
  const mb = $('btn-mode');
  mb.classList.toggle('enforce', mode === 'enforce');
  mb.innerHTML = I('power', 'sm') + '<span>' + (mode === 'enforce' ? 'Enforcing' : 'Observe only') + '</span>';
  mb.title = 'Anti-cheat mode: ' + (mode || '-') + ' (click to switch)';
}

const PAGES = {};
const DRAWERS = {};

/* ================================================================== DASHBOARD */
function chartSvg(points) {
  const W = 1000, H = 250, pad = 8;
  if (points.length < 2) return '<div class="empty"><b>Collecting data</b>The server samples the player count every 5 minutes.</div>';
  const max = Math.max(4, ...points.map((p) => p.n));
  const t0 = points[0].at, t1 = points[points.length - 1].at || t0 + 1;
  const xy = points.map((p) => [pad + (W - pad * 2) * ((p.at - t0) / Math.max(1, t1 - t0)), H - pad - (H - pad * 2) * (p.n / max)]);
  let d = 'M' + xy[0][0].toFixed(1) + ' ' + xy[0][1].toFixed(1);
  for (let i = 0; i < xy.length - 1; i += 1) {
    const p0 = xy[i - 1] || xy[i], p1 = xy[i], p2 = xy[i + 1], p3 = xy[i + 2] || p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ' C' + c1[0].toFixed(1) + ' ' + c1[1].toFixed(1) + ' ' + c2[0].toFixed(1) + ' ' + c2[1].toFixed(1) + ' ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
  }
  const area = d + ' L' + xy[xy.length - 1][0].toFixed(1) + ' ' + (H - pad) + ' L' + xy[0][0].toFixed(1) + ' ' + (H - pad) + ' Z';
  let grid = '';
  for (let g = 0; g <= 4; g += 1) { const y = pad + (H - pad * 2) * g / 4; grid += '<line x1="0" x2="' + W + '" y1="' + y + '" y2="' + y + '" stroke="#1a2437" stroke-width="1" stroke-dasharray="4 6"/>'; }
  return '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"><defs><linearGradient id="gl" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2dd4bf"/><stop offset="1" stop-color="#6366f1"/></linearGradient><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2dd4bf" stop-opacity=".22"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient></defs>' +
    grid + '<path d="' + area + '" fill="url(#ga)"/><path d="' + d + '" fill="none" stroke="url(#gl)" stroke-width="2.4" vector-effect="non-scaling-stroke"/></svg>';
}
PAGES.dashboard = () => {
  const o = S.data.overview;
  if (!o) return loading();
  const act = arr(o.activity);
  const peak = act.reduce((m, p) => Math.max(m, p.n || 0), 0);
  const avg = act.length ? Math.round(act.reduce((s, p) => s + (p.n || 0), 0) / act.length) : 0;
  const e = o.entities || {};
  const stat = (k, v, cls, s, pct, bar) => '<div class="card stat-card"><div class="k">' + h(k) + '</div><div class="v ' + (cls || '') + '">' + h(v) + '</div>' +
    (pct != null ? '<div class="meter"><i class="' + (bar || '') + '" style="width:' + Math.max(0, Math.min(100, pct)) + '%"></i></div>' : '') + '<div class="s"><span>' + h(s || '') + '</span></div></div>';
  const recent = arr(o.joins).map((j) => ({ at: j.at, icon: j.kind === 'join' ? 'pulse' : 'out', act: j.kind === 'join' ? 'Join' : 'Left', user: j.name, reason: j.reason }))
    .concat(arr(o.recent).filter((r) => r.stream !== 'entity').map((r) => ({ at: r.at, icon: 'radar', act: 'Detection', user: r.name, reason: (r.label || r.kind) + (r.detail ? ' -- ' + r.detail : ''), det: r.id })))
    .sort((a, b) => (secs(b.at) || 0) - (secs(a.at) || 0)).slice(0, 12);
  const rows = recent.map((r) => '<tr' + (r.det ? ' class="click" data-act="det" data-id="' + h(r.det) + '"' : '') + '><td><span class="act-cell">' + I(r.icon, 'sm') + h(r.act) + '</span></td><td>' + h(r.user || '-') +
    '</td><td class="wrapcell muted">' + h(r.reason || '') + '</td><td class="right muted">' + h(ago(r.at)) + '</td></tr>');
  const host = o.hostname || S.info.server || 'Server';
  return '<div class="card server-card"><div style="flex:1 1 auto;min-width:0"><h1>' + h(host) + ' <span class="chip-on">Online</span><span class="chip-blue">' + I('users', 'sm') + h(num(o.online)) + '/' + h(num(o.maxSlots)) + '</span>' +
      (o.mode === 'enforce' ? '<span class="chip-red">Enforcing</span>' : '<span class="chip-blue">Observe only</span>') + '</h1>' +
      '<p>NexusAC v' + h(o.version || '') + ' &middot; up ' + h(dur(o.uptime)) + ' &middot; website ' + h(o.website && o.website.connected ? 'connected' : (o.website && o.website.configured ? 'not reachable' : 'not configured')) + '</p></div>' +
      (can('config') ? '<button class="btn" data-act="mode-toggle">' + I('power', 'sm') + (o.mode === 'enforce' ? 'Switch to observe' : 'Switch to enforce') + '</button>' : '') + '</div>' +
    '<div class="grid four" style="margin-top:18px">' +
      stat('Players online', num(o.online), 'blue', 'of ' + num(o.maxSlots) + ' slots', o.maxSlots ? o.online / o.maxSlots * 100 : 0) +
      stat('Under watch', num(o.watched), o.watched ? 'amber' : '', num(o.scored) + ' with any risk', o.online ? o.watched / Math.max(1, o.online) * 100 : 0, 'amber') +
      stat('Isolated', num(o.isolated || 0), o.isolated ? 'red' : '', 'held in their own bucket', o.online ? (o.isolated || 0) / Math.max(1, o.online) * 100 : 0, 'red') +
      stat('Entities denied', num(e.denied), 'green', num(e.created) + ' created this session', e.created ? e.denied / Math.max(1, e.created) * 100 : 0, 'green') +
    '</div>' +
    '<div class="card"><h3>Player Activity<small>Last 24 hours</small></h3>' + chartSvg(act) +
      '<div class="legend"><span><i class="dot"></i>Peak: ' + h(peak) + '</span><span><i class="dot" style="background:var(--blue)"></i>Avg: ' + h(avg) + '</span></div></div>' +
    '<div class="card"><h3>Recent Actions<small>' + recent.length + ' items</small></h3>' +
      table(['Action', 'User', 'Reason', '>Time'], rows, empty('Nothing yet', 'Joins, leaves and detections show up here.'), ['150px', '22%', 'auto', '150px']) + '</div>';
};

/* ================================================================== PLAYERS */
function statusBadges(p) {
  const b = [];
  if (p.staff) b.push(badge('Admin', 'amber'));
  if (p.frozen) b.push(badge('frozen', 'blue'));
  if (p.contained) b.push(badge('isolated', 'red'));
  if (p.lifecycle && String(p.lifecycle).toLowerCase() !== 'active') b.push(badge(String(p.lifecycle).toLowerCase(), 'faint'));
  return b.join(' ');
}
PAGES.players = () => {
  const rows = S.data.players;
  if (!rows) return loading();
  let list = filterRows(arr(rows), S.filters.players, ['name', 'src', 'lifecycle']);
  if (S.staffOnly) list = list.filter((p) => p.staff);
  list = list.slice().sort((a, b) => (b.risk || 0) - (a.risk || 0) || a.src - b.src);
  const cards = list.map((p) => '<button class="pcard" data-act="player" data-src="' + h(p.src) + '"><i class="dot ' + ((p.risk || 0) >= 60 ? 'off' : ((p.risk || 0) > 0 ? 'amber' : '')) + '"></i>' +
    '<div class="who"><b>[' + h(p.src) + '] ' + h(p.name) + '</b><small><span class="' + pingCls(p.ping) + '">' + h(num(p.ping)) + 'ms</span>' + statusBadges(p) + '</small></div>' +
    '<span class="' + riskCls(p.risk) + '" title="Risk">' + h(num(p.risk || 0)) + '</span></button>').join('');
  return '<div class="page-head">' + search('players', 'Search...') + '<button class="btn' + (S.staffOnly ? ' primary' : '') + '" data-act="staff-only">View Staff</button><span class="spacer"></span>' +
      '<span class="badge" style="padding:6px 12px;font-size:12.5px">' + arr(rows).length + ' Players online</span></div>' +
    (cards ? '<div class="pgrid">' + cards + '</div>' : '<div class="card">' + empty('No players', 'Nobody matches.') + '</div>');
};
function playerRow(src) { return arr(S.data.players).find((p) => String(p.src) === String(src)); }
DRAWERS.player = () => {
  const p = playerRow(S.playerSrc);
  const d = S.data.player && String(S.data.player.src) === String(S.playerSrc) ? S.data.player : null;
  if (!p) return drawerShell('Player', empty('Player left', 'This player is no longer connected.'));
  const acts = [];
  if (can('spectate')) acts.push('<button class="btn" data-act="p-spectate">' + I('eye', 'sm') + 'Spectate</button>');
  if (can('stream')) acts.push('<button class="btn" data-act="p-screen">Live screen</button>');
  if (can('view_evidence')) acts.push('<button class="btn" data-act="p-shot">Screenshot</button>');
  if (can('freeze')) acts.push('<button class="btn" data-act="p-freeze">' + (p.frozen ? 'Unfreeze' : 'Freeze') + '</button>');
  if (can('warn')) acts.push('<button class="btn" data-act="p-warn">' + I('warn', 'sm') + 'Warn</button>');
  if (can('kick')) acts.push('<button class="btn danger" data-act="p-kick">' + I('out', 'sm') + 'Kick</button>');
  if (can('ban')) acts.push('<button class="btn danger" data-act="p-ban">' + I('ban', 'sm') + 'Ban</button>');
  const info = kv([
    ['Server ID', p.src], ['Name', p.name], ['Ping', num(p.ping) + ' ms'], ['Risk', num(p.risk)],
    ['Trust', p.trust == null ? '-' : num(p.trust) + ' / 100'], ['Signals', num(p.signals)], ['Lifecycle', p.lifecycle],
    ['Health', p.health != null ? num(p.health) + (p.armour != null ? ' / armour ' + num(p.armour) : '') : null],
    ['Ped', p.ped], ['Speed', p.speed != null ? num(p.speed, 1) + ' m/s' : null], ['Routing bucket', p.bucket],
    ['Session', p.sessionAge != null ? dur(p.sessionAge) : null],
  ]);
  let detail = '<section>' + empty('Loading details', '') + '</section>';
  if (d) {
    const sigs = arr(d.signals || d.recent || []).slice().reverse().slice(0, 25).map((e) => '<tr><td>' + h(ago(e.at)) + '</td><td>' + h(e.kind) + '</td><td>' + h(num(e.counted != null ? e.counted : e.weight)) + '</td><td class="wrapcell muted">' + h(e.detail || '') + '</td></tr>');
    detail = '<section><h4>Recent detections</h4>' + table(['When', 'Kind', '+', 'Detail'], sigs, empty('No detections', ''), ['110px', '30%', '40px', 'auto']) + '</section>' +
      (d.state ? '<section><h4>State</h4>' + kv(scalars(d.state)) + '</section>' : '');
  }
  return drawerShell('[' + p.src + '] ' + p.name,
    '<section><h4>Actions</h4><div class="actions-grid">' + (acts.join('') || '<span class="dim">No actions for your role.</span>') + '</div></section>' +
    '<section><h4>Player</h4>' + info + (statusBadges(p) ? '<div class="row" style="margin-top:10px">' + statusBadges(p) + '</div>' : '') + '</section>' + detail);
};
function playerCmd(type, extra) {
  const p = playerRow(S.playerSrc);
  if (!p) return toast(false, 'That player is not online.');
  exec(Object.assign({ type, target: p.src, session: p.sessionKey }, extra || {}));
}

/* ================================================================== SPECTATE */
PAGES.spectate = () => {
  const n = S.data.nex;
  const o = S.data.overview || {};
  const players = arr(S.data.players);
  const strip = '<div class="strip">' +
    '<div class="st">' + I('pulse', 'sm') + 'Online <b>' + h(num(o.online != null ? o.online : players.length)) + '</b></div>' +
    '<div class="st">' + I('warn', 'sm') + 'Suspects <b>' + h(num(o.watched || 0)) + '</b></div>' +
    '<div class="st">' + I('eye', 'sm') + 'Isolated <b>' + h(num(o.isolated || 0)) + '</b></div>' +
    '<div class="st" style="border-right:0">' + I('shield', 'sm') + 'Admins <b>' + h(num(o.admins || 0)) + '</b></div></div>';
  const toolbar = '<div class="toolbar"><span class="act-cell">' + I('sliders', 'sm') + 'Layout</span>' +
    [1, 2, 3].map((c) => '<button class="icon-btn' + (S.spLayout === c ? ' on' : '') + '" data-act="sp-layout" data-n="' + c + '">' + I('g' + c, 'sm') + '</button>').join('') +
    '<span class="spacer"></span><button class="btn" data-act="refresh">' + I('refresh', 'sm') + 'Refresh</button></div>';
  if (!n) return strip + toolbar + loading();
  if (n.enabled === false) return strip + toolbar + '<div class="card">' + empty('Live screens are unavailable', 'The screenshot-basic resource is not running, or your role cannot stream.') + '</div>';
  const watching = arr(n.watching);
  const watchingIds = watching.map((w) => String(w.src));
  const tiles = watching.map((w) => {
    const f = S.nexFrames[w.src];
    const p = playerRow(w.src) || {};
    return '<div class="screen"><div class="head"><span class="dim mono">#' + h(w.src) + '</span><b>' + h(w.name) + '</b>' + (p.staff ? badge('Admin', 'amber') : '') + badge(w.live ? 'live' : 'starting', w.live ? 'green' : 'faint') + '</div>' +
      '<div class="frame">' + (f && f.frame ? '<img id="nex-img-' + h(w.src) + '" src="' + h(f.frame) + '">' :
        '<img id="nex-img-' + h(w.src) + '" class="hidden"><div class="wait" id="nex-wait-' + h(w.src) + '">Waiting for the first frame...</div>') + '</div>' +
      '<div class="foot"><button class="btn small" data-act="player" data-src="' + h(w.src) + '">Player</button><button class="btn small" data-act="nex-stop" data-src="' + h(w.src) + '">Stop</button><span class="spacer"></span>' +
      (p.ping != null ? '<span class="' + pingCls(p.ping) + '">&#9679; ' + h(num(p.ping)) + 'ms</span>' : '') + '</div></div>';
  }).join('');
  const f = S.spFilter;
  let pool = filterRows(players, S.filters.spectate, ['name', 'src']);
  if (f === 'suspect') pool = pool.filter((p) => (p.risk || 0) > 0);
  else if (f === 'isolated') pool = pool.filter((p) => p.contained);
  else if (f === 'admin') pool = pool.filter((p) => p.staff);
  const item = (p, on) => '<button class="rail-item' + (on ? ' sel' : '') + '" data-act="' + (on ? 'nex-stop' : 'nex-watch') + '" data-src="' + h(p.src) + '"><div class="who"><b>' + h(p.name) + '</b><small>#' + h(p.src) +
    ' <span class="' + pingCls(p.ping) + '">' + h(num(p.ping)) + 'ms</span></small></div>' + (p.staff ? badge('Admin', 'amber') : '') + ((p.risk || 0) > 0 ? badge('risk ' + num(p.risk), 'red') : '') + '</button>';
  const selected = pool.filter((p) => watchingIds.includes(String(p.src)));
  const rest = pool.filter((p) => !watchingIds.includes(String(p.src)));
  const fb = (id, label) => '<button class="btn small' + (f === id ? ' primary' : '') + '" data-act="sp-filter" data-f="' + id + '">' + label + '</button>';
  return strip + toolbar + '<div class="spect"><div class="stage">' +
    (watching.length ? '<div class="screens c' + S.spLayout + '">' + tiles + '</div>' : '<div class="card">' + empty('Not watching anyone', 'Pick players on the right. Up to ' + num(n.maxPerAdmin || 4) + ' at once; streams stop by themselves when you leave this page.') + '</div>') +
    '</div><div class="rail"><div class="row2">' + fb('all', 'All') + fb('suspect', 'Suspect') + fb('isolated', 'Isolated') + fb('admin', 'Admin') + '</div>' +
    '<button class="btn wide" data-act="nex-reset"' + (watching.length ? '' : ' disabled') + '>Stop all (' + watching.length + ')</button>' +
    search('spectate', 'Search by name or ID...') +
    '<div class="rail-head">Selected (' + selected.length + ')</div><div class="rail-list">' + selected.map((p) => item(p, true)).join('') + '</div>' +
    '<div class="rail-head">All (' + rest.length + ')</div><div class="rail-list">' + rest.map((p) => item(p, false)).join('') + '</div></div></div>';
};
function nexFrame(d) {
  if (!d) return;
  if (d.stopped) { delete S.nexFrames[d.stopped]; if (S.tab === 'spectate') request('nex'); return; }
  if (!d.src || !d.frame) return;
  S.nexFrames[d.src] = { frame: d.frame, seq: d.seq, name: d.name };
  nexShow(d.src);
}
// Decode off-screen first, then swap: the tile never shows a half-decoded or
// empty frame. While one frame decodes, only the newest waiting one is kept.
const nexDecoding = {};
function nexShow(src) {
  if (nexDecoding[src]) { nexDecoding[src] = 'again'; return; }
  const f = S.nexFrames[src];
  if (!f) return;
  nexDecoding[src] = true;
  const frame = f.frame;
  const pre = new Image();
  pre.src = frame;
  const swap = () => {
    const img = $('nex-img-' + src);
    if (img) {
      img.src = frame;
      img.classList.remove('hidden');
      const wait = $('nex-wait-' + src);
      if (wait) wait.parentNode.removeChild(wait);
    }
    const again = nexDecoding[src] === 'again';
    nexDecoding[src] = false;
    if (again && S.nexFrames[src] && S.nexFrames[src].frame !== frame) nexShow(src);
  };
  (pre.decode ? pre.decode() : Promise.resolve()).then(swap, swap);
}

/* ================================================================== DETECTIONS */
function acted(r) { return (r.counted || 0) > 0 && !r.observed; }
function sevBadge(r) {
  if (r.stream === 'entity') return badge('blocked', 'blue');
  return acted(r) ? badge('Enforced +' + num(r.counted), 'red') : badge(r.observed ? 'Logged only' : 'Recorded', 'faint');
}
PAGES.detections = () => {
  const rows = S.data.feed;
  if (!rows) return loading();
  let list = filterRows(arr(rows), S.filters.detections, ['name', 'kind', 'label', 'detail', 'src', 'detector']);
  if (S.detSev === 'acted') list = list.filter(acted);
  else if (S.detSev === 'logged') list = list.filter((r) => !acted(r) && r.stream !== 'entity');
  else if (S.detSev === 'entity') list = list.filter((r) => r.stream === 'entity');
  const trs = list.map((r) => '<tr class="click det-row" data-act="det" data-id="' + h(r.id || '') + '" data-at="' + h(r.at) + '" data-src="' + h(r.src) + '"><td class="muted">' + h(ago(r.at)) + '</td><td><span class="act-cell" style="font-weight:500"><i class="dot ' + (r.online ? '' : 'dim') + '"></i>' + h(r.name || '-') + ' <span class="dim">#' + h(r.src) + '</span></span></td>' +
    '<td><b>' + h(r.label || r.kind) + '</b><div class="dim mono">' + h(r.kind) + '</div></td><td class="mono dim">' + h(r.detector || '-') + '</td><td>' + sevBadge(r) + '</td><td class="wrapcell muted">' + h(r.detail || '') + '</td></tr>');
  return head('Detections', list.length) +
    '<div class="bar-card">' + search('detections', 'Search player, detection, detector or detail...') +
      sel('data-act-change="det-sev"', [['all', 'All results'], ['acted', 'Enforced'], ['logged', 'Logged only'], ['entity', 'Blocked entities']], S.detSev, '180px') + '</div>' +
    '<div class="card" style="padding:8px 10px">' + table(['When', 'Player', 'Detection', 'Detector', 'Result', 'Detail'], trs, empty('No detections', 'That is the normal state on a clean server.'), ['140px', '18%', '20%', '130px', '130px', 'auto']) + '</div>';
};
function feedRow(id, at, src) {
  return arr(S.data.feed).find((r) => (id && String(r.id) === String(id)) || (!id && String(r.at) === String(at) && String(r.src) === String(src)));
}
function banFor(r) {
  return arr(S.data.bans).find((b) => (r.license && arr(b.identifiers).includes(r.license)) || (!r.license && r.name && b.name === r.name));
}
DRAWERS.det = () => {
  const r = S.detId;
  if (!r) return drawerShell('Detection', empty('Not found', 'This detection has rotated out of the recent list.'));
  const online = r.online && playerRow(r.src);
  const ban = banFor(r);
  const acts = [];
  if (online) {
    acts.push('<button class="btn" data-act="player" data-src="' + h(r.src) + '">' + I('user', 'sm') + 'Open player</button>');
    if (can('spectate')) acts.push('<button class="btn" data-act="d-cmd" data-cmd="spectate" data-src="' + h(r.src) + '">' + I('eye', 'sm') + 'Spectate</button>');
    if (can('view_evidence')) acts.push('<button class="btn" data-act="d-cmd" data-cmd="screenshot" data-src="' + h(r.src) + '">Screenshot</button>');
    if (can('kick')) acts.push('<button class="btn danger" data-act="d-cmd" data-cmd="kick" data-src="' + h(r.src) + '">' + I('out', 'sm') + 'Kick</button>');
    if (can('ban')) acts.push('<button class="btn danger" data-act="d-cmd" data-cmd="ban" data-src="' + h(r.src) + '">' + I('ban', 'sm') + 'Ban</button>');
  }
  if (ban && can('unban')) acts.push('<button class="btn primary" data-act="unban" data-id="' + h(ban.banId || ban.identifier) + '" data-name="' + h(ban.name || '') + '">Unban</button>');
  if (r.detector) acts.push('<button class="btn" data-act="prot" data-id="' + h(r.detector) + '">' + I('gear', 'sm') + 'Detector settings</button>');
  const measures = scalars(r.extra || {});
  const evid = arr(S.data.evidence).filter((e) => r.name && e.player === r.name).slice(0, 8)
    .map((e) => '<tr class="click" data-act="ev" data-id="' + h(e.id) + '"><td class="muted">' + h(ago(e.at)) + '</td><td>' + h(e.detection) + '</td><td>' + badge(e.action || '-', e.action === 'ban' || e.action === 'kick' ? 'red' : 'faint') + '</td></tr>');
  return drawerShell(r.label || r.kind,
    '<section><div class="row" style="margin-bottom:12px">' + sevBadge(r) + (r.detector ? badge(r.detector, 'faint') : '') + badge(r.kind, 'faint') + '<span class="spacer"></span><span class="muted">' + h(when(r.at)) + '</span></div>' +
      '<div class="detail-big">' + h(r.detail || 'No detail recorded.') + '</div>' +
      (r.why ? '<p class="muted" style="margin:10px 0 0">Why it did not act: ' + h(r.why) + '</p>' : '') + '</section>' +
    (measures.length ? '<section><h4>Measurements</h4>' + kv(measures) + '</section>' : '') +
    '<section><h4>Player</h4>' + kv([['Name', r.name], ['Server ID', r.src], ['Status', online ? 'online' : (ban ? 'banned' : 'offline')], ['Identifier', r.license],
      ['Risk after this', r.risk != null ? num(r.risk) : null], ['Weight', r.weight != null ? num(r.weight) : null]]) +
      (ban ? '<div class="card" style="margin-top:12px;padding:14px 16px"><b>Banned</b> <span class="dim mono">' + h(ban.banId || '') + '</span><div class="muted" style="margin-top:4px">' + h(ban.reason || '') + '</div>' +
        '<div class="dim" style="margin-top:6px;font-size:12px">' + h(when(ban.at)) + ' &middot; ' + h(ban.expires ? 'until ' + when(ban.expires) : 'permanent') + '</div></div>' : '') + '</section>' +
    '<section><h4>Actions</h4><div class="actions-grid">' + (acts.join('') || '<span class="dim">Nothing to do: the player is offline and not banned.</span>') + '</div></section>' +
    (can('view_evidence') ? '<section><h4>Evidence for this player</h4>' + table(['When', 'Detection', 'Action'], evid, empty('No evidence cases', ''), ['130px', 'auto', '90px']) + '</section>' : ''));
};

/* ================================================================== BANS */
function banStatus(b) {
  if (!b.expires) return 'permanent';
  return secs(b.expires) < Date.now() / 1000 ? 'expired' : 'temporary';
}
PAGES.bans = () => {
  const rows = S.data.bans;
  if (!rows) return loading();
  let list = filterRows(arr(rows), S.filters.bans, ['name', 'banId', 'reason', 'identifier']).sort((a, b) => (b.at || 0) - (a.at || 0));
  if (S.banStatus !== 'all') list = list.filter((b) => banStatus(b) === S.banStatus);
  const tools = sel('data-act-change="ban-view"', [['card', 'Card View'], ['table', 'Table View']], S.banView, '150px');
  const unban = (b) => can('unban') ? '<button class="btn small" data-act="unban" data-id="' + h(b.banId || b.identifier) + '" data-name="' + h(b.name || '') + '">Unban</button>' : '';
  const stBadge = (b) => { const s = banStatus(b); return badge(s, s === 'permanent' ? 'red' : (s === 'expired' ? 'faint' : 'amber')); };
  // Ban screenshots (sv_banshots.lua): frames load when the drawer opens.
  const shotBtn = (b) => {
    const sh = b.shots;
    if (!sh || !can('view_evidence')) return '';
    if (sh.status === 'captured') return '<button class="btn small" data-act="ban-shots" data-id="' + h(b.banId) + '">' + I('eye', 'sm') + (sh.clip ? 'Clip + ' : '') + 'Screenshots (' + h(num(sh.n || 0)) + ')</button>';
    if (sh.status === 'requested') return badge('capturing', 'faint');
    return '<span title="' + h(sh.status) + '">' + badge('no screenshot', 'faint') + '</span>';
  };
  let body;
  if (!list.length) body = '<div class="empty" style="padding-top:20px">No bans found.</div>';
  else if (S.banView === 'table') {
    body = '<div class="card" style="padding:8px 10px">' + table(['Ban ID', 'Name', 'Reason', 'Banned', 'Status', ''], list.map((b) => '<tr><td class="mono">' + h(b.banId || '-') + '</td><td>' + h(b.name || '-') + '</td><td class="wrapcell muted">' + h(b.reason || '') +
      '</td><td class="muted">' + h(when(b.at)) + '</td><td>' + stBadge(b) + '</td><td class="right">' + shotBtn(b) + ' ' + unban(b) + '</td></tr>'), null, ['120px', '16%', 'auto', '130px', '110px', '230px']) + '</div>';
  } else {
    body = '<div class="grid cards">' + list.map((b) => '<div class="card ban-card"><div class="top"><b>' + h(b.name || 'Unknown') + '</b>' + stBadge(b) + '</div>' +
      '<div class="reason">' + h(b.reason || 'No reason') + '</div><div class="meta"><span class="mono">' + h(b.banId || '-') + '</span><span>' + h(ago(b.at)) + '</span></div>' +
      '<div class="row" style="margin-top:12px"><span class="dim" style="font-size:12px">' + h(arr(b.identifiers).length) + ' identifiers &middot; ' + h(b.expires ? 'until ' + when(b.expires) : 'permanent') + '</span><span class="spacer"></span>' + shotBtn(b) + ' ' + unban(b) + '</div></div>').join('') + '</div>';
  }
  return head('Bans', list.length, tools) +
    '<div class="bar-card">' + search('bans', 'Search all fields...') +
      sel('data-act-change="ban-status"', [['all', 'All Status'], ['permanent', 'Permanent'], ['temporary', 'Temporary'], ['expired', 'Expired']], S.banStatus, '160px') +
      '<button class="btn" data-act="ban-clear">Clear Filters</button></div><div style="height:18px"></div>' + body;
};

/* ================================================================== KICKS / WARNS / AUDIT */
const PUNISH_ICON = { ban: 'ban', kick: 'out', warn: 'warn', unban: 'shield' };
function punishTable(list) {
  const trs = list.map((r) => { const k = r.kind || r.action || r.type || '-'; return '<tr><td><span class="act-cell">' + I(PUNISH_ICON[k] || 'audit', 'sm') + h(k.charAt(0).toUpperCase() + k.slice(1)) + '</span></td><td>' + h(r.name || r.player || '-') +
    '</td><td class="wrapcell muted">' + h(r.reason || r.detail || '') + '</td><td>' + h(r.by || r.admin || '-') + (r.auto ? ' ' + badge('auto', 'faint') : '') + '</td><td class="right muted">' + h(ago(r.at || r.time)) + '</td></tr>'; });
  return '<div class="card" style="padding:8px 10px">' + table(['Action', 'User', 'Reason', 'By', '>Time'], trs, empty('Nothing recorded', ''), ['130px', '18%', 'auto', '16%', '150px']) + '</div>';
}
function punishPage(kind, t) {
  const rows = S.data.punishments;
  if (!rows) return loading();
  const list = filterRows(arr(rows).filter((r) => (r.kind || r.action || r.type) === kind), S.filters[kind], ['name', 'reason', 'by']);
  return head(t, list.length) + '<div class="bar-card">' + search(kind, 'Search name, reason or staff...') + '</div><div style="height:18px"></div>' + punishTable(list);
}
PAGES.kicks = () => punishPage('kick', 'Kicks');
PAGES.warns = () => punishPage('warn', 'Warns');
PAGES.audit = () => {
  const rows = S.data.punishments;
  if (!rows) return loading();
  let list = filterRows(arr(rows), S.filters.audit, ['name', 'reason', 'by', 'kind']);
  if (S.auditKind !== 'all') list = list.filter((r) => (r.kind || r.action || r.type) === S.auditKind);
  return head('Audit Log', null, '', 'Every warn, kick, ban and unban, by staff or by NexusAC, newest first.') +
    '<div class="bar-card">' + search('audit', 'Search...') + sel('data-act-change="audit-kind"', [['all', 'All actions'], ['ban', 'Bans'], ['kick', 'Kicks'], ['warn', 'Warns'], ['unban', 'Unbans']], S.auditKind, '160px') + '</div><div style="height:18px"></div>' + punishTable(list);
};

/* ================================================================== PROTECTION */
const CAT_INFO = {
  Combat: ['cross', 'Detects combat exploits like aimbot, silent aim, magic bullets, damage boost and infinite ammo.'],
  Movement: ['move', 'Detects movement exploits like noclip, teleport, fast run, super jump and freecam.'],
  Entities: ['car', 'Stops spawned props, vehicles and peds, entity griefing and vehicle cheats.'],
  Player: ['user', 'Protects from godmode, revive, armour, invisibility and appearance cheats.'],
  Resources: ['box', 'Prevents resource tampering, injection, executors and stopped resources.'],
  Network: ['pulse', 'Blocks event abuse, crash payloads and network floods.'],
};
function catInfo(c) { return CAT_INFO[c] || ['shield', 'Protection modules in this category.']; }
function protRow(id) { return arr(S.data.protections).find((p) => p.id === id); }
function protExpected(p) { return { enabled: p.enabled, profile: p.profile, action: p.action, minConfidence: p.minConfidence, screenshot: p.screenshot, discord: p.discord }; }

/* The 2026-10-09 modules: config switches (sv_config SCHEMA), not Protection Center entries. */
const MODULES = [
  { group: 'Testing & enforcement', icon: 'sliders', info: 'How hard NexusAC acts, and switches for testing cheats on yourself.', items: [
    ['general.adminWhitelist', 'Admin whitelist', 'Off = staff are detected like players. Turn off to test cheats; a detection WILL ban you.'],
    ['protection.banOnFirstDetection', 'Ban on first detection', 'Every detector bans on its first finding.'],
    ['bubble.untouchableMinAttackers', 'Bubble test: shooters needed', '2 normally. 1 lets a single friend shooting you trigger it (testing only).'],
  ] },
  { group: 'Combat', icon: 'cross', info: 'Aim, damage and weapon cheats.', items: [
    ['weaponitem.enabled', 'Anti Weapon Spawning', 'A gun in hand that is not in their ox_inventory: removed + ban.'],
    ['damageboost.enabled', 'Anti Damage Boost / One-Hit Kill', 'Body shots taking more health than the gun can do, or one-shot body kills.'],
    ['bubble.untouchable', 'Anti Bubble (cannot be shot)', 'Other players\' clean body shots never register on them.'],
    ['explosions.blockAll', 'Block ALL explosions', 'Lockdown: every explosion, rocket, grenade, sticky bomb and fire is cancelled server-side, explosive weapons are taken, and players are explosion/fire proof.'],
    ['explosions.spam', 'Anti Explosion Spam', 'Explosion spam, explosions set off on players from far away, explosions blamed on others.'],
    ['sensors.antiHeadshot', 'Anti Headshot', 'Critical hits switched off on their own ped.'],
    ['sensors.aimlock', 'Anti Aimbot (memory)', 'Camera turns onto heads with no mouse input.'],
    ['sensors.magic', 'Anti Magic Bullets', 'Hits from a player whose game fired far fewer shots.'],
    ['combat.enabled', 'Combat (server)', 'Kill-all, server silent aim, trigger timing.'],
    ['triggernex.enabled', 'Anti TriggerBot', 'Shots fired with no trigger held.'],
    ['aimnex.enabled', 'Anti Aimbot (Aim NEX)', 'Camera turning onto targets with no mouse input.'],
    ['silent5.enabled', 'Anti Silent Aim (NEX 2)', 'Hits on players the crosshair line was never on.'],
    ['ammonex.enabled', 'Anti Infinite Ammo', 'Shots that never use ammo.'],
  ] },
  { group: 'Movement', icon: 'move', info: 'Speed, flight and camera cheats.', items: [
    ['fastrun.enabled', 'Anti Fast Run', 'Sprinting faster than the game allows.'],
    ['sensors.spinbot', 'Anti Spinbot', 'Ped spinning while the camera stays still.'],
    ['sensors.gravity', 'Anti Jetpack / Zero Gravity', 'Airborne with gravity switched off.'],
    ['sensors.roll', 'Anti Infinite Combat Roll', 'Rolls chained with no cooldown.'],
    ['sensors.stamina', 'Anti Infinite Stamina', 'Stamina that never drains.'],
    ['freecam.enabled', 'Anti Freecam', 'Camera far away from the ped.'],
    ['state.enabled', 'Noclip / teleport / super jump', 'Server position checks.'],
  ] },
  { group: 'Player & vehicles', icon: 'user', info: 'Godmode, revive, armour and vehicle cheats.', items: [
    ['vehiclespawn.enabled', 'Anti Vehicle Spawning', 'GTA cars/helis no script hands out and the player does not own: deleted + ban on the first spawn. Add-on cars are never judged.'],
    ['blackhole.enabled', 'Anti Black Hole', 'Cars, NPCs or props pulled into one spot: ban.'],
    ['godmode.enabled', 'Anti Godmode', 'Damage ignored, proofs, health locks.'],
    ['playerguard.enabled', 'Anti Revive / Armour', 'Self revive and armour with no grant.'],
    ['vehiclegodmode.enabled', 'Anti Vehicle Godmode', 'A car that cannot be damaged.'],
    ['vehicles.enabled', 'Vehicle rules', 'Vehicle spawns and modifications.'],
    ['entity.enabled', 'Entity firewall', 'Spawned props, peds and vehicles.'],
  ] },
  { group: 'Vision', icon: 'shield', info: 'Wallhack / ESP protection.', items: [
    ['fow.enabled', 'Anti Wallhack (Fog of War)', 'Hides players behind walls from every client, so wallhacks and ESP see nothing (sentra-fow). Off = stopped, everyone shown.'],
  ] },
  { group: 'Client & FPS', icon: 'cpu', info: 'Client-side modules that cost players FPS.', items: [
    ['reticle.light', 'Light aim tracker', 'On = only the shot frame is measured (best FPS).'],
    ['sensors.enabled', 'Sensors (all client sensors)', 'Master switch for the sensor reports.'],
  ] },
];
function moduleRow(path, label, info) {
  const c = S.data.config;
  const s = c && c.settings && c.settings[path];
  if (!s) return '';
  const edit = can('config');
  let ctrl;
  if (s.kind === 'boolean') {
    ctrl = '<button class="switch' + (s.value ? ' on' : '') + '" data-act="set-bool" data-path="' + h(path) + '"' + (edit ? '' : ' disabled') + '></button>';
  } else {
    const key = 'set:' + path;
    const val = Object.prototype.hasOwnProperty.call(S.drafts, key) ? S.drafts[key] : s.value;
    ctrl = '<input class="input" type="number" style="width:70px;height:32px" id="mod-' + path.replace(/[^a-zA-Z0-9]/g, '_') + '" data-set="' + h(path) + '" value="' + h(val) + '"' + (s.lo != null ? ' min="' + s.lo + '"' : '') + (s.hi != null ? ' max="' + s.hi + '"' : '') + '>' +
      '<button class="btn small" data-act="set-save" data-path="' + h(path) + '">Save</button>';
  }
  const on = s.kind !== 'boolean' || s.value;
  return '<div class="prow"><i class="dot ' + (on ? '' : 'off') + '"></i><div class="name"><b>' + h(label || s.label || path) + (s.live ? '' : ' <span class="badge faint restart">restart</span>') + '</b><small>' + h(info || s.note || path) + '</small></div>' + ctrl + '</div>';
}
function protTabs() {
  const c = S.data.protections ? arr(S.data.protections).length : 0;
  const b = (id, icon, label, n) => '<button class="' + (S.protTab === id ? 'on' : '') + '" data-act="prot-tab" data-t="' + id + '">' + I(icon, 'sm') + label + (n != null ? '<span class="n">' + n + '</span>' : '') + '</button>';
  return '<div class="tabs">' + b('detections', 'shield', 'Detectors', c) + b('modules', 'sliders', 'Modules', null) +
    (can('entity_rules') ? b('lists', 'ban', 'Black / White Lists', null) : '') +
    (can('config') ? b('settings', 'gear', 'Settings', null) : '') + (can('punishments') ? b('signals', 'bars', 'Signal Actions', null) : '') + '</div>';
}
PAGES.protection = () => {
  const tools = '';
  if (S.protTab === 'modules') {
    if (!S.data.config) return '<div class="page-head">' + protTabs() + '</div>' + loading();
    const cols = MODULES.map((g) => {
      const rows = g.items.map(([p, l, i]) => moduleRow(p, l, i)).join('');
      if (!rows) return '';
      return '<div class="cat"><div class="ch">' + I(g.icon) + h(g.group) + '<span class="n">' + g.items.length + '</span></div><div class="cd">' + h(g.info) + '</div>' + rows + '</div>';
    }).join('');
    return '<div class="page-head">' + protTabs() + '<span class="spacer"></span>' + tools + '</div>' +
      '<div class="page-sub" style="margin-top:0">Switches marked <span class="badge faint">restart</span> take effect for players after NexusAC restarts (or they reconnect). Changes are saved and kept across restarts.</div>' +
      '<div class="grid cols">' + cols + '</div>';
  }
  if (S.protTab === 'signals') return '<div class="page-head">' + protTabs() + '</div>' + signalsBody();
  if (S.protTab === 'settings') return '<div class="page-head">' + protTabs() + '</div>' + settingsBody();
  if (S.protTab === 'lists') return '<div class="page-head">' + protTabs() + '</div>' + listsBody();
  const rows = S.data.protections;
  if (!rows) return '<div class="page-head">' + protTabs() + '</div>' + loading();
  let list = filterRows(arr(rows), S.filters.protection, ['name', 'id', 'category', 'info']);
  const cats = [...new Set(arr(rows).map((p) => p.category || 'Other'))].sort();
  if (S.protCat) list = list.filter((p) => (p.category || 'Other') === S.protCat);
  const groups = {};
  list.forEach((p) => { (groups[p.category || 'Other'] = groups[p.category || 'Other'] || []).push(p); });
  const edit = can('config');
  const cols = Object.keys(groups).sort().map((g) => {
    const items = groups[g].sort((a, b) => String(a.name).localeCompare(String(b.name)));
    const ci = catInfo(g);
    return '<div class="cat"><div class="ch">' + I(ci[0]) + h(g) + '<span class="n">' + items.length + '</span></div><div class="cd">' + h(ci[1]) + '</div>' +
      items.map((p) => '<div class="prow"><i class="dot ' + (p.enabled ? (p.mode === 'observe' ? 'amber' : '') : 'off') + '" title="' + h(p.enabled ? p.mode : 'disabled') + '"></i>' +
        '<div class="name" data-act="prot" data-id="' + h(p.id) + '"><b>' + h(p.name) + '</b><small>' + h(p.id) + (p.health && p.health.flags ? ' &middot; ' + h(num(p.health.players)) + ' flagged today' : '') + '</small>' +
        (p.enabled && p.logWhy && p.logWhy.length ? '<small style="color:var(--amber)">Only logging: ' + h(p.logWhy.join('; ')) + '</small>' : '') + '</div>' +
        '<button class="icon-btn more" data-act="prot" data-id="' + h(p.id) + '" title="Settings">' + I('more', 'sm') + '</button>' +
        (p.enabled ? sel('data-act-change="prot-action" data-id="' + h(p.id) + '"' + (!edit || p.locked ? ' disabled' : ''), [['log', 'Log'], ['kick', 'Kick'], ['ban', 'Ban']], p.action) : '') +
        '<button class="switch' + (p.enabled ? ' on' : '') + '" data-act="prot-toggle" data-id="' + h(p.id) + '"' + (!edit || p.locked ? ' disabled' : '') + '></button></div>').join('') + '</div>';
  }).join('');
  return '<div class="page-head">' + protTabs() + '</div>' +
    '<div class="bar-card">' + search('protection', 'Search detections...') + sel('data-act-change="prot-cat"', [['', 'All Categories']].concat(cats.map((c) => [c, c])), S.protCat, '200px') + '</div><div style="height:18px"></div>' +
    (cols ? '<div class="grid cols">' + cols + '</div>' : '<div class="card">' + empty('No detectors match', '') + '</div>');
};
DRAWERS.prot = () => {
  const p = protRow(S.protId);
  if (!p) return drawerShell('Detector', empty('Loading', 'Asking the server for this detector...'));
  const d = S.drafts['prot:' + p.id] || protExpected(p);
  const editable = can('config') && !p.locked;
  const dis = editable ? '' : ' disabled';
  const pick = (name, opts, cur) => '<select class="select" data-pd="' + name + '"' + dis + '>' + opts.map((o) => '<option value="' + o + '"' + (o === cur ? ' selected' : '') + '>' + o.charAt(0).toUpperCase() + o.slice(1) + '</option>').join('') + '</select>';
  const facts = (t, obj) => { const pairs = scalars(obj); return pairs.length ? '<section><h4>' + h(t) + '</h4>' + kv(pairs) + '</section>' : ''; };
  const hl = p.health;
  const health = hl ? '<section><h4>Health today' + (hl.spike ? ' &middot; spike' : '') + '</h4>' + kv([
    ['Flags today', num(hl.flags)], ['Players flagged', num(hl.players)], ['Share of players', num(hl.share) + '%'],
    ['Players online today', num(hl.population)], ['Usual per day', hl.avgPlayers == null ? 'no history yet' : num(hl.avgPlayers)],
  ]) + (hl.spike ? '<p class="muted" style="margin:8px 0 0">Far more players than usual. Check these findings for false positives.</p>' : '') + '</section>' : '';
  return drawerShell(p.name,
    '<section><p class="muted" style="margin:0 0 12px">' + h(p.info || '') + '</p>' + kv([['ID', p.id], ['Category', p.category], ['Evidence', p.evidence], ['Maturity', p.maturity], ['Mode', p.mode]]) + '</section>' +
    '<section><h4>Settings</h4><div class="form">' +
      '<div class="row between"><span>Protection enabled</span><button class="switch' + (d.enabled ? ' on' : '') + '" data-act="pd-toggle" data-key="enabled"' + dis + '></button></div>' +
      '<label class="field"><span>Detector mode (observe records only, enforce acts)</span>' + pick('mode', ['disabled', 'observe', 'enforce'], p.mode || 'enforce').replace('data-pd="mode"', 'data-pmode="1"') + '</label>' +
      '<label class="field"><span>Detection profile</span>' + pick('profile', ['relaxed', 'balanced', 'strict'], d.profile) + '</label>' +
      '<label class="field"><span>Enforcement</span>' + pick('action', ['log', 'kick', 'ban'], d.action) + '</label>' +
      '<label class="field"><span>Minimum confidence: <b id="pd-conf">' + h(num(d.minConfidence)) + '%</b></span><input type="range" min="50" max="100" value="' + h(d.minConfidence) + '" data-pd="minConfidence"' + dis + '></label>' +
      '<div class="row between"><span>Evidence screenshot</span><button class="switch' + (d.screenshot ? ' on' : '') + '" data-act="pd-toggle" data-key="screenshot"' + dis + '></button></div>' +
      '<div class="row between"><span>Discord notification</span><button class="switch' + (d.discord ? ' on' : '') + '" data-act="pd-toggle" data-key="discord"' + dis + '></button></div>' +
      (editable ? '<div class="row" style="justify-content:flex-end"><button class="btn" data-act="pd-reset">Reset</button><button class="btn primary" data-act="pd-save">Save</button></div>' : '<p class="dim">This detector is locked or your role cannot change it.</p>') +
    '</div></section>' + health + facts('Live counters', p.stats) + facts('Thresholds', p.thresholds));
};
/* Black / white lists. Each list = the server's defaults (GTA vehicles, the
   default troll-prop blacklist, the props server scripts use) plus the
   Entity Rules set here (ban = blacklist, allow = whitelist). Removing a
   default moves it to the other side as a rule. */
const LISTS = [
  { key: 'bl-veh', title: 'Blacklisted vehicles', policy: 'ban', kind: 'vehicle', icon: 'car',
    info: 'Spawning one = banned on the first spawn. Every GTA vehicle is on it by default; add add-on cars too.' },
  { key: 'wl-veh', title: 'Whitelisted vehicles', policy: 'allow', kind: 'vehicle', icon: 'car',
    info: 'Never gets anyone banned, even GTA vehicles. Use it for job or garage cars your scripts spawn.' },
  { key: 'bl-obj', title: 'Blacklisted objects', policy: 'ban', kind: 'object', icon: 'box',
    info: 'Props and peds that ban on the first spawn. Known menu troll props are on it by default.' },
  { key: 'wl-obj', title: 'Whitelisted objects', policy: 'allow', kind: 'object', icon: 'box',
    info: 'Always allowed. The props your server scripts use are on it by default.' },
];
const LIST_SHOW = 120;
function ruleKind(r) { return r.kind || (r.class === 'vehicle' ? 'vehicle' : 'object'); }
function listRows(L) {
  const rules = arr(S.data.config && S.data.config.entities);
  const d = S.data.lists || {};
  const byName = {};
  rules.forEach((r) => { if (r.name) byName[String(r.name).toLowerCase()] = r; });
  const mine = (r) => (ruleKind(r) === 'vehicle') === (L.kind === 'vehicle');
  const out = rules.filter((r) => r.policy === L.policy && mine(r)).map((r) => ({ name: r.name || r.hash, hash: r.hash, src: 'yours' }));
  const seen = {};
  out.forEach((r) => { seen[String(r.name).toLowerCase()] = true; });
  const add = (name, tag) => {
    const k = String(name).toLowerCase();
    if (seen[k]) return;
    const rule = byName[k];
    if (rule && rule.policy !== L.policy) return;   // moved to the other side by a rule
    seen[k] = true;
    out.push({ name, src: tag });
  };
  if (L.key === 'bl-veh' && d.strict) arr(d.gta).forEach((g) => add(g[0], 'GTA ' + (g[1] || 'vehicle')));
  if (L.key === 'wl-veh') arr(d.vehAllow).forEach((n) => add(n, 'config.lua'));
  if (L.key === 'bl-obj') arr(d.objBlack).forEach((o) => add(o[0], o[1] === 'config' ? 'config.lua' : 'default'));
  if (L.key === 'wl-obj') arr(d.objAllow).forEach((n) => add(n, 'server script'));
  return out;
}
function listsBody() {
  if (!S.data.config || !S.data.lists) return loading();
  const edit = can('entity_rules');
  const cards = LISTS.map((L) => {
    const all = listRows(L);
    const q = (S.filters['list-' + L.key] || '').trim().toLowerCase();
    const hits = q ? all.filter((r) => String(r.name).toLowerCase().includes(q)) : all;
    hits.sort((x, y) => (x.src === 'yours' ? 0 : 1) - (y.src === 'yours' ? 0 : 1) || String(x.name).localeCompare(String(y.name)));
    const items = hits.slice(0, LIST_SHOW).map((r) => '<div class="prow"><i class="dot ' + (L.policy === 'ban' ? 'off' : '') + '"></i><div class="name"><b>' + h(r.name) + '</b><small>' +
      h(r.src === 'yours' ? 'added by staff' : r.src) + '</small></div>' +
      (edit && r.src !== 'config.lua' ? '<button class="icon-btn more" data-act="list-remove" data-key="' + L.key + '" data-model="' + h(r.hash || r.name) + '" data-name="' + h(r.name) + '" data-from="' + h(r.src) + '" title="Remove">' + I('x', 'sm') + '</button>' : '') + '</div>').join('');
    const draft = S.drafts['list:' + L.key] || '';
    return '<div class="cat"><div class="ch">' + I(L.icon) + h(L.title) + '<span class="n">' + all.length + '</span></div><div class="cd">' + h(L.info) + '</div>' +
      (edit ? '<div class="row" style="margin-bottom:8px"><input class="input" id="list-in-' + L.key + '" data-list="' + L.key + '" value="' + h(draft) + '" placeholder="Add a spawn code, e.g. ' + (L.kind === 'vehicle' ? 'adder' : 'prop_barrier_work05') + '" style="flex:1 1 auto">' +
        '<button class="btn primary" data-act="list-add" data-key="' + L.key + '">Add</button></div>' : '') +
      '<div class="row" style="margin-bottom:6px">' + search('list-' + L.key, 'Search this list...') + '</div>' +
      '<div style="max-height:420px;overflow-y:auto">' + (items || '<div class="empty" style="padding:16px">' + (q ? 'Nothing matches.' : 'Nothing on this list yet.') + '</div>') + '</div>' +
      (hits.length > LIST_SHOW ? '<div class="dim" style="font-size:12px;padding:8px 6px 0">Showing ' + LIST_SHOW + ' of ' + hits.length + ' -- search to find the rest.</div>' : '') + '</div>';
  }).join('');
  return '<div class="page-sub" style="margin-top:0">Type a spawn code and press Add (or Enter). Blacklist = banned on the first spawn. Whitelist = never banned for it. Removing a default moves it to the other list. Changes are live and saved.</div>' +
    '<div class="grid two">' + cards + '</div>';
}
function listAdd(key) {
  const L = LISTS.find((x) => x.key === key);
  const input = $('list-in-' + key);
  const model = String((input && input.value) || S.drafts['list:' + key] || '').trim();
  if (!L) return;
  if (!model) return toast(false, 'Type a spawn code first.');
  if (!/^[A-Za-z0-9_\-]{2,64}$/.test(model)) return toast(false, 'Spawn codes are letters, numbers and underscores.');
  exec({ type: 'entity', model, policy: L.policy, kind: L.kind });
  delete S.drafts['list:' + key];
  if (input) input.value = '';
  setTimeout(() => { request('config'); request('lists'); }, 400);
}

function signalsBody() {
  const c = S.data.config;
  if (!c) return loading();
  const all = arr(c.kinds);
  const changed = all.filter((k) => k.action && k.action !== 'risk').length;
  let list = filterRows(all, S.filters.signals, ['kind', 'label']);
  if (S.sigChanged) list = list.filter((k) => k.action && k.action !== 'risk');
  const opts = ['risk', 'log', 'kick', 'ban', 'none'];
  const trs = list.map((k) => '<tr><td>' + h(k.label || k.kind) + '</td><td class="mono dim">' + h(k.kind) + '</td><td>' + h(num(k.weight)) + '</td><td>' +
    '<select class="select" style="width:100%;max-width:210px" data-act-change="punish" data-kind="' + h(k.kind) + '" data-expected="' + h(k.action) + '">' +
    opts.map((o) => '<option value="' + o + '"' + (o === k.action ? ' selected' : '') + '>' + (o === 'risk' ? 'default (module decides)' : o) + '</option>').join('') + '</select></td></tr>');
  return '<div class="bar-card">' + search('signals', 'Search signals...') +
      '<button class="btn small' + (S.sigChanged ? '' : ' primary') + '" data-act="sig-show" data-v="all">All (' + all.length + ')</button>' +
      '<button class="btn small' + (S.sigChanged ? ' primary' : '') + '" data-act="sig-show" data-v="changed">Changed (' + changed + ')</button></div>' +
    '<div class="page-sub" style="margin:10px 0 8px">Default = the module (Protection page) decides. Anything else here wins for that one signal. Saved instantly.</div>' +
    '<div class="card" style="padding:8px 10px">' + table(['Signal', 'Kind', 'Weight', 'Action'], trs, empty('No signals match', ''), ['auto', '26%', '80px', '220px']) + '</div>';
}

/* ================================================================== EVIDENCE */
PAGES.evidence = () => {
  const rows = S.data.evidence;
  if (!rows) return loading();
  const list = filterRows(arr(rows), S.filters.evidenceLocal, ['player', 'detection', 'detector', 'id', 'action']);
  const trs = list.map((e) => '<tr class="click" data-act="ev" data-id="' + h(e.id) + '"><td class="muted">' + h(when(e.at)) + '</td><td>' + h(e.player || '-') + ' <span class="dim">#' + h(e.src == null ? '-' : e.src) +
    '</span></td><td><b>' + h(e.detection) + '</b></td><td class="mono dim">' + h(e.detector || '-') + '</td><td>' + h(e.confidence == null ? '-' : num(e.confidence) + '%') + '</td><td>' + badge(e.action || '-', e.action === 'ban' || e.action === 'kick' ? 'red' : 'faint') +
    '</td><td>' + badge(e.shot || 'none', 'faint') + '</td></tr>');
  return head('Evidence', list.length) + '<div class="bar-card">' + search('evidence', 'Search player, detection, case...') + '</div><div style="height:18px"></div>' +
    '<div class="card" style="padding:8px 10px">' + table(['When', 'Player', 'Detection', 'Detector', 'Confidence', 'Action', 'Screenshot'], trs, empty('No evidence', 'Nothing has been recorded yet.'), ['130px', '16%', 'auto', '140px', '95px', '90px', '110px']) + '</div>';
};
/* Ban screenshots: THE frame (closest to the detection) large, every frame in
   time order below it -- negative = before the ban, positive = after. */
function bsLabel(f, d) {
  const t = Number(f.t) || 0;
  const s = (t < 0 ? '-' : '+') + (Math.abs(t) / 1000).toFixed(1) + 's';
  return s + (t < 0 ? ' before the ban' : ' after the ban');
}
DRAWERS.banshots = () => {
  const d = S.data.banShots && S.data.banShots.banId === S.banShotId ? S.data.banShots : null;
  if (!d) return drawerShell('Screenshots', empty('Loading frames', 'Fetching them from the server...'));
  const ban = arr(S.data.bans).find((b) => b.banId === d.banId) || {};
  if (d.status !== 'captured') return drawerShell('Screenshots', empty('No screenshots for this ban', d.why || d.status || ''));
  const frames = arr(d.frames);
  const best = Math.max(0, (Number(d.best) || 1) - 1);
  const sel = S.banShotSel != null && frames[S.banShotSel] ? S.banShotSel : best;
  const f = frames[sel];
  const before = frames.filter((x) => Number(x.t) < 0).length;
  const strip = frames.map((x, i) => '<button class="bs-thumb' + (i === sel ? ' sel' : '') + (i === best ? ' best' : '') + '" data-act="bs-pick" data-i="' + i + '">' +
    '<img src="' + h(x.data) + '"><span>' + h(bsLabel(x, d).split(' ')[0]) + (i === best ? ' &middot; detection' : '') + '</span></button>').join('');
  return drawerShell(ban.name || d.name || 'Screenshots',
    '<section>' + kv([['Ban', d.banId], ['Reason', ban.reason || d.reason], ['Detector', d.detector], ['When', when(d.at)], ['Ping', d.ping != null ? num(d.ping) + ' ms' : null],
      ['Frames', num(frames.length) + (before ? ' (' + num(before) + ' from before the ban)' : ' (all taken as the ban landed -- the before-buffer is off)')]]) + '</section>' +
    (d.clip ? '<section><h4>Clip</h4><video class="bs-clip" src="' + h(d.clip) + '" controls autoplay muted loop playsinline></video></section>'
      : (d.clipError ? '<section><p class="muted" style="margin:0">No clip: ' + h(d.clipError) + '</p></section>' : '')) +
    '<section><h4>' + (sel === best ? 'Closest frame to the detection' : 'Frame') + ' &middot; ' + h(bsLabel(f, d)) + '</h4>' +
      '<button class="bs-main" data-act="bs-full" data-i="' + sel + '" title="Open full size"><img src="' + h(f.data) + '"></button></section>' +
    '<section><h4>Timeline</h4><div class="bs-strip">' + strip + '</div></section>');
};
DRAWERS.ev = () => {
  const e = S.data.evidenceItem && S.data.evidenceItem.id === S.evidenceId ? S.data.evidenceItem : null;
  if (!e) return drawerShell('Evidence', empty('Loading case', ''));
  const pl = e.player || {};
  const sigs = arr(e.signals).slice(0, 30).map((x) => '<tr><td class="muted">' + h(ago(x.at)) + '</td><td>' + h(x.kind) + '</td><td class="wrapcell muted">' + h(x.detail || '') + '</td></tr>');
  const det = e.detail && typeof e.detail === 'object' ? e.detail : null;
  return drawerShell(e.detection || 'Evidence',
    '<section>' + kv([['Case', e.id], ['When', when(e.at)], ['Player', (pl.name || '-') + (pl.src != null ? ' (#' + pl.src + ')' : '')],
      ['Detector', e.detector], ['Confidence', e.confidence == null ? '-' : num(e.confidence) + '%'], ['Needed', e.needed == null ? null : num(e.needed) + '%'],
      ['Trust', e.trust], ['Action', e.action], ['Screenshot', e.screenshot && e.screenshot.status]]) + '</section>' +
    (det && scalars(det).length ? '<section><h4>Measurements</h4>' + kv(scalars(det)) + '</section>' : '') +
    '<section><h4>Detections</h4>' + table(['When', 'Kind', 'Detail'], sigs, empty('No detections attached', ''), ['120px', '30%', 'auto']) + '</section>' +
    '<section><h4>Raw detail</h4><pre class="json">' + h(pretty(e.detail)) + '</pre></section>');
};

/* ================================================================== LOGS */
PAGES.logs = () => {
  const rows = S.data.logs;
  if (!rows) return loading();
  const list = filterRows(arr(rows), S.filters.logs, ['category', 'title', 'text', 'kind', 'level', (r) => pretty(r.fields || '')]);
  const trs = list.map((r) => {
    const text = r.text || r.detail || (Array.isArray(r.fields) ? r.fields.map((f) => Array.isArray(f) ? f[0] + ': ' + f[1] : pretty(f)).join(' | ') : '');
    return '<tr><td class="muted">' + h(when(r.at)) + '</td><td>' + badge(r.level || '-', r.level === 'alert' ? 'red' : (r.level === 'warn' ? 'amber' : 'faint')) + '</td><td>' + h(r.category || '-') + '</td><td>' + h(r.title || r.kind || '-') +
      '</td><td class="wrapcell muted">' + h(text) + '</td></tr>';
  });
  return head('Logs', list.length) + '<div class="bar-card">' + search('logs', 'Search logs...') + '</div><div style="height:18px"></div>' +
    '<div class="card" style="padding:8px 10px">' + table(['When', 'Level', 'Category', 'Title', 'Detail'], trs, empty('No log entries', ''), ['130px', '80px', '110px', '20%', 'auto']) + '</div>';
};

/* ================================================================== RESOURCES */
PAGES.resources = () => {
  const d = S.data.resources;
  if (!d) return loading();
  const all = arr(d.resources);
  const started = all.filter((r) => r.state === 'started').length;
  const stopped = all.length - started;
  let res = filterRows(all, S.filters.resources, ['name', 'state', 'author', 'description']);
  if (S.resState) res = res.filter((r) => (S.resState === 'started') === (r.state === 'started'));
  const evByRes = {};
  arr(d.events).forEach((e) => { evByRes[e.resource] = (evByRes[e.resource] || 0) + 1; });
  const maxEv = Math.max(1, ...Object.values(evByRes));
  const CAP_LABEL = { teleport: 'teleports', godmode: 'godmode', heal: 'heal/revive', armour: 'armour', weapons: 'weapons', vehicles: 'vehicles',
    objects: 'objects', peds: 'peds', invisible: 'invisibility', collision: 'collision/freeze', speed: 'speed', model: 'ped model', money: 'money',
    items: 'items', explosions: 'explosions', buckets: 'buckets', spectate: 'spectate', damage: 'damage mods', handling: 'handling', attach: 'attach' };
  const HOT = { teleport: 1, godmode: 1, money: 1, items: 1, weapons: 1, explosions: 1, damage: 1, invisible: 1 };
  const intelHtml = (r) => {
    const i = r.intel;
    if (!i) return '';
    const caps = Object.keys(i.caps || {}).sort((a, b) => (HOT[b] || 0) - (HOT[a] || 0));
    return '<div class="row" style="gap:5px;flex-wrap:wrap;margin-top:8px">' +
      (i.escrowed ? badge('escrowed' + (i.encrypted ? ' (' + i.encrypted + ' files)' : ''), 'amber') : badge('open source', 'faint')) +
      caps.map((c) => badge(CAP_LABEL[c] || c, HOT[c] ? 'red' : 'blue')).join('') +
      (i.coords ? badge(i.coords + ' map spots', 'faint') : '') + '</div>';
  };
  const cards = res.map((r) => '<div class="card res-card"><div class="top"><b title="' + h(r.name) + '">' + h(r.name) + '</b>' + badge(r.state === 'started' ? 'Started' : r.state, r.state === 'started' ? 'white' : 'faint') + '</div>' +
    '<div class="by">' + h(r.author || r.description || '') + '</div>' + intelHtml(r) +
    '<div class="line">' + I('bolt', 'sm') + 'Events<span class="v blue">' + h(num(evByRes[r.name] || 0)) + '</span></div><div class="meter"><i style="width:' + ((evByRes[r.name] || 0) / maxEv * 100) + '%"></i></div>' +
    '<div class="line">' + I('tag', 'sm') + 'Version<span class="v">' + h(r.version || '-') + '</span></div>' + resButtons(r) + '</div>').join('');
  return '<div class="bar-card">' + search('resources', 'Search resources...') + sel('data-act-change="res-state"', [['', 'All Status'], ['started', 'Started'], ['stopped', 'Not started']], S.resState || '', '160px') + '</div>' +
    '<div class="grid three" style="margin-top:18px">' +
      '<div class="card stat-card"><div class="k">Resources started</div><div class="v">' + h(num(started)) + '</div><div class="meter"><i class="white" style="width:' + (all.length ? started / all.length * 100 : 0) + '%"></i></div><div class="s"><span>of ' + h(num(all.length)) + ' total resources</span><span>' + h(num(stopped)) + ' stopped</span></div></div>' +
      '<div class="card stat-card"><div class="k">Registered events</div><div class="v blue">' + h(num(d.eventTotal || arr(d.events).length)) + '</div><div class="meter"><i style="width:100%"></i></div><div class="s"><span>net events the server listens to</span></div></div>' +
      '<div class="card stat-card"><div class="k">Resource intelligence</div><div class="v green">' + h(num((d.intel || {}).resources || 0)) + ' profiled</div><div class="meter"><i class="green" style="width:100%"></i></div><div class="s"><span>' +
        h(num((d.intel || {}).escrowed || 0)) + ' escrowed</span><span>' + h(num((d.intel || {}).knownRoutes || 0)) + ' learned routes, ' + h(num((d.intel || {}).explained || 0)) + ' teleports explained</span></div></div>' +
    '</div><div class="grid cards" style="margin-top:18px">' + (cards || empty('No resources match', '')) + '</div>';
};

/* Start / stop / restart from the card. NexusAC itself is console-only. */
function resButtons(r) {
  if (!can('config') || r.name === RES) return '';
  const on = r.state === 'started' || r.state === 'starting';
  const b = (op, label, cls) => '<button class="btn small' + (cls ? ' ' + cls : '') + '" data-act="res-op" data-op="' + op + '" data-name="' + h(r.name) + '">' + label + '</button>';
  return '<div class="row" style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line)">' +
    (on ? b('restart', I('refresh', 'sm') + 'Restart') + b('stop', I('power', 'sm') + 'Stop', 'danger')
        : b('start', I('power', 'sm') + 'Start', 'primary')) + '</div>';
}

/* ================================================================== SETTINGS */
function settingGroups(settings) {
  const groups = {};
  Object.keys(settings || {}).forEach((path) => { const g = path.split('.')[0]; (groups[g] = groups[g] || []).push(path); });
  Object.values(groups).forEach((l) => l.sort());
  return groups;
}
function settingControl(path, s) {
  const key = 'set:' + path;
  const val = Object.prototype.hasOwnProperty.call(S.drafts, key) ? S.drafts[key] : s.value;
  const dirty = Object.prototype.hasOwnProperty.call(S.drafts, key) && S.drafts[key] !== s.value;
  const idAttr = 'set-' + path.replace(/[^a-zA-Z0-9]/g, '_');
  let ctrl;
  if (s.kind === 'boolean') ctrl = '<button class="switch' + (val ? ' on' : '') + '" data-act="set-bool" data-path="' + h(path) + '"></button>';
  else if (s.values) ctrl = '<select class="select" id="' + idAttr + '" data-set="' + h(path) + '">' + Object.keys(s.values).sort().map((v) => '<option value="' + h(v) + '"' + (String(v) === String(val) ? ' selected' : '') + '>' + h(v) + '</option>').join('') + '</select>';
  else if (s.kind === 'number') ctrl = '<input class="input" type="number" id="' + idAttr + '" data-set="' + h(path) + '" value="' + h(val) + '"' + (s.lo != null ? ' min="' + h(s.lo) + '"' : '') + (s.hi != null ? ' max="' + h(s.hi) + '"' : '') + '>';
  else if ((s.maxLen || 0) > 200) ctrl = '<textarea class="textarea" id="' + idAttr + '" data-set="' + h(path) + '" maxlength="' + h(s.maxLen) + '">' + h(val) + '</textarea>';
  else ctrl = '<input class="input" id="' + idAttr + '" data-set="' + h(path) + '" value="' + h(val) + '"' + (s.maxLen ? ' maxlength="' + h(s.maxLen) + '"' : '') + '>';
  const save = s.kind === 'boolean' ? '' : '<button class="btn small' + (dirty ? ' primary' : '') + '" data-act="set-save" data-path="' + h(path) + '"' + (dirty ? '' : ' disabled') + '>Save</button>';
  return '<div class="setting"><div class="about"><b>' + h(s.label || path) + (s.live ? '' : ' <span class="badge faint">restart</span>') + '</b><small>' + h(s.note || path) +
    (s.lo != null || s.hi != null ? ' &middot; range ' + h(s.lo == null ? '' : s.lo) + ' to ' + h(s.hi == null ? '' : s.hi) : '') + '</small></div><div class="ctrl">' + ctrl + save + '</div></div>';
}
function settingsBody() {
  const c = S.data.config;
  if (!c) return loading();
  const groups = settingGroups(c.settings);
  const names = Object.keys(groups).sort();
  const q = (S.filters.settings || '').trim().toLowerCase();
  let paths;
  if (q) paths = Object.keys(c.settings).filter((p) => (p + ' ' + (c.settings[p].label || '') + ' ' + (c.settings[p].note || '')).toLowerCase().includes(q)).sort();
  else { if (!S.settingsGroup || !groups[S.settingsGroup]) S.settingsGroup = names[0]; paths = groups[S.settingsGroup] || []; }
  const pers = c.persistence || {};
  const nav = names.map((g) => '<button class="' + (!q && g === S.settingsGroup ? 'on' : '') + '" data-act="set-group" data-group="' + h(g) + '">' + h(g) + ' <span class="dim">' + groups[g].length + '</span></button>').join('');
  return '<div class="page-sub" style="margin-top:0">Live settings, saved on the server and kept across restarts' + (pers.lastError ? ' (last save error: ' + pers.lastError + ')' : '') + '.</div>' +
    '<div class="bar-card">' + search('settings', 'Search all settings...') + '</div><div style="height:18px"></div>' +
    '<div class="settings-layout"><div class="settings-nav">' + nav + '</div><div><div class="card">' +
    (paths.length ? paths.map((p) => settingControl(p, c.settings[p])).join('') : empty('No settings match', '')) + '</div>' +
    '<div class="card"><h3>Recent changes</h3>' + table(['When', 'By', 'What', 'From', 'To'], arr(c.history).slice(0, 20).map((x) => '<tr><td class="muted">' + h(when(x.at)) + '</td><td>' + h(x.by || '-') + '</td><td class="wrapcell">' + h(x.what || x.path || '-') +
      '</td><td class="wrapcell muted">' + h(x.from == null ? '-' : typeof x.from === 'object' ? pretty(x.from) : x.from) + '</td><td class="wrapcell">' + h(x.to == null ? '-' : typeof x.to === 'object' ? pretty(x.to) : x.to) + '</td></tr>'),
      empty('No changes yet', ''), ['130px', '16%', 'auto', '16%', '16%']) + '</div></div></div>';
}

/* ================================================================== WEBHOOKS */
PAGES.webhooks = () => {
  const w = S.data.webhooks;
  if (!w) return loading();
  const cards = arr(w.channels).map((ch) => '<div class="card"><h3>' + h(ch.category) + ' ' + badge(ch.configured ? (ch.status || 'configured') : 'not set', ch.configured ? 'green' : 'faint') + '</h3>' +
    kv([['Destination', ch.displayUrl || ch.directDisplayUrl || 'none'], ['Sent', num(ch.sent || 0)], ['Failed', num(ch.failed || 0)], ['Last sent', ch.lastAt ? ago(ch.lastAt) : '-'], ['Last error', ch.lastError]]) +
    '<div class="row" style="margin-top:12px"><input class="input" id="wh-' + h(ch.category) + '" placeholder="https://discord.com/api/webhooks/..." style="flex:1 1 auto">' +
    '<button class="btn primary" data-act="wh-save" data-cat="' + h(ch.category) + '">Save</button>' +
    (ch.configuredDirect ? '<button class="btn" data-act="wh-clear" data-cat="' + h(ch.category) + '">Clear</button>' : '') + '</div></div>').join('');
  return head('Webhooks', null, '', 'Discord channels per category. URLs are stored in the panel storage and never shown in full.' + (w.queued ? ' ' + w.queued + ' deliveries waiting.' : '')) +
    (cards ? '<div class="grid two">' + cards + '</div>' : '<div class="card">' + empty('No webhook categories', '') + '</div>');
};

/* ================================================================== ADMIN WHITELIST */
/* Players NexusAC never acts on (treated like staff). Add an online player
   (every identifier they have is stored) or a typed identifier for someone
   offline. Saved in the panel storage; live for everyone at once. */
PAGES.whitelist = () => {
  const d = S.data.whitelist;
  if (!d) return loading();
  const edit = d.canEdit && can('config');
  const entries = filterRows(arr(d.entries), S.filters.whitelist, ['name', 'key', 'note', 'byName']);
  const warn = d.enabled ? '' : '<div class="card" style="border-color:#f59e0b55;margin-bottom:14px"><b>The Admin whitelist switch is OFF</b>' +
    '<p class="muted" style="margin:6px 0 0">Everyone -- staff and the players below -- is judged like a normal player until it is switched back on (Configuration &gt; General &gt; Admin whitelist).</p></div>';
  const online = arr(d.online);
  const pick = online.filter((p) => !p.whitelisted);
  const addCard = !edit ? '' : '<div class="grid two" style="margin-bottom:14px">' +
    '<div class="card"><h3>Add an online player</h3><p class="muted" style="margin:0 0 10px">Stores every identifier they have (licence, Discord, FiveM, Steam...).</p>' +
      (pick.length ? '<div class="row" style="gap:8px;flex-wrap:wrap"><select class="input" id="wl-online" style="flex:1 1 180px">' +
        pick.map((p) => '<option value="' + h(p.src) + '">#' + h(p.src) + ' ' + h(p.name || '?') + (p.ace ? ' (staff ace)' : '') + '</option>').join('') + '</select>' +
        '<input class="input" id="wl-note" maxlength="120" placeholder="Note (why)" style="flex:1 1 160px">' +
        '<button class="btn primary" data-act="wl-add-online">Whitelist</button></div>'
        : empty('Nobody to add', 'Every online player is already whitelisted.')) + '</div>' +
    '<div class="card"><h3>Add by identifier</h3><p class="muted" style="margin:0 0 10px">For someone offline: license:..., discord:..., fivem:... or steam:...</p>' +
      '<div class="row" style="gap:8px;flex-wrap:wrap"><input class="input mono" id="wl-key" maxlength="120" placeholder="license:abc123..." style="flex:2 1 220px">' +
      '<input class="input" id="wl-name" maxlength="64" placeholder="Name" style="flex:1 1 120px">' +
      '<input class="input" id="wl-note2" maxlength="120" placeholder="Note" style="flex:1 1 120px">' +
      '<button class="btn primary" data-act="wl-add-id">Whitelist</button></div></div></div>';
  const trs = entries.map((e) => '<tr><td><b>' + h(e.name || '-') + '</b>' + (e.online ? ' ' + badge('online #' + e.online, 'green') : '') + '</td>' +
    '<td class="mono wrapcell" style="font-size:12px">' + h(e.key) + (arr(e.ids).length ? '<br><span class="dim">+' + h(arr(e.ids).length) + ' more: ' + h(arr(e.ids).join(', ')) + '</span>' : '') + '</td>' +
    '<td class="wrapcell muted">' + h(e.note || '') + '</td><td>' + h(e.byName || '-') + '</td><td class="muted">' + h(e.at ? ago(e.at) : '-') + '</td>' +
    '<td class="right">' + (edit ? '<button class="btn small" data-act="wl-remove" data-id="' + h(e.key) + '" data-name="' + h(e.name || e.key) + '">Remove</button>' : '') + '</td></tr>');
  const staffOnline = online.filter((p) => p.staff && !p.whitelisted);
  return head('Admin Whitelist', entries.length, '', 'Players NexusAC never acts on: no detections, no automatic kicks or bans, every bypass. Staff with the nexus.bypass ace or an ESX admin group are already exempt.') +
    warn + addCard +
    '<div class="bar-card">' + search('whitelist', 'Search name, identifier, note...') + '</div><div style="height:14px"></div>' +
    '<div class="card" style="padding:8px 10px">' + table(['Player', 'Identifier', 'Note', 'Added by', 'Added', ''], trs,
      empty('Nobody is whitelisted', 'Add a player above.'), ['18%', 'auto', '20%', '12%', '110px', '90px']) + '</div>' +
    (staffOnline.length ? '<p class="muted" style="margin-top:12px">Online and already exempt as staff: ' + staffOnline.map((p) => h(p.name || ('#' + p.src))).join(', ') + '</p>' : '');
};

/* ================================================================== EVENT PROTECTION */
PAGES.events = () => {
  const d = S.data.eventRules;
  if (!d) return loading();
  const rules = filterRows(arr(d.rules), S.filters.events, ['name', 'mode', 'source']).sort((a, b) => String(a.name).localeCompare(String(b.name)));
  const edit = can('event_rules');
  const trs = rules.map((r) => '<tr><td class="mono wrapcell">' + h(r.name) + '</td><td>' + badge(r.mode, r.mode === 'ignore' ? 'faint' : 'amber') + '</td><td>' + h(r.mode === 'watch' ? num(r.perMinute) + '/min' : '-') +
    '</td><td>' + h(num(r.accepted || 0)) + '</td><td>' + h(num(r.exceeded || 0)) + '</td><td>' + badge(r.custom ? 'custom' : (r.source || 'built-in'), 'faint') +
    '</td><td class="right">' + (edit ? '<button class="btn small" data-act="ev-edit" data-name="' + h(r.name) + '">Edit</button>' + (r.custom ? ' <button class="btn small" data-act="ev-del" data-name="' + h(r.name) + '">Delete</button>' : '') : '') + '</td></tr>');
  const tools = (edit ? '<button class="btn primary" data-act="ev-add">Add rule</button><button class="btn" data-act="ev-import">Import</button>' : '') + '<button class="btn" data-act="ev-export">Export</button>';
  return head('Event Protection', rules.length, tools, 'Rate rules for server events: watch (flag over a rate) or ignore.') +
    '<div class="bar-card">' + search('events', 'Search events...') + '</div><div style="height:18px"></div>' +
    '<div class="card" style="padding:8px 10px">' + table(['Event', 'Mode', 'Rate', 'Accepted', 'Exceeded', 'Source', ''], trs, empty('No event rules', ''), ['auto', '90px', '90px', '90px', '90px', '100px', '160px']) + '</div>';
};
function eventRuleModal(rule) {
  confirmAction({
    title: rule ? 'Edit rule' : 'Add event rule', reason: false, ok: 'Save',
    text: 'watch: flag a player who triggers this event faster than the rate. ignore: never flag it.',
    extra: '<div class="form"><label class="field"><span>Event name</span><input class="input" data-mv="name" value="' + h(rule ? rule.name : '') + '"' + (rule ? ' readonly' : '') + '></label>' +
      '<label class="field"><span>Mode</span><select class="select" data-mv="mode"><option value="watch"' + (!rule || rule.mode === 'watch' ? ' selected' : '') + '>watch</option><option value="ignore"' + (rule && rule.mode === 'ignore' ? ' selected' : '') + '>ignore</option></select></label>' +
      '<label class="field"><span>Rate per minute (watch)</span><input class="input" type="number" min="1" max="1000" data-mv="perMinute" value="' + h(rule ? rule.perMinute || 60 : 60) + '"></label></div>',
    onOk: (_, v) => exec({ type: 'eventRule', operation: 'save', name: v.name.trim(), mode: v.mode, perMinute: Math.floor(Number(v.perMinute) || 0) }),
  });
}

/* ================================================================== ENTITY RULES */
PAGES.entities = () => {
  const c = S.data.config;
  if (!c) return loading();
  const lk = S.data.lookup;
  const rules = filterRows(arr(c.entities), S.filters.entities, ['name', 'hash', 'policy']);
  const pol = (cur, model) => '<select class="select" data-act-change="entity" data-model="' + h(model) + '" data-expected="' + h(cur) + '">' +
    ['allow', 'block', 'ban'].map((o) => '<option value="' + o + '"' + (o === cur ? ' selected' : '') + '>' + o + '</option>').join('') + '</select>';
  const trs = rules.map((r) => '<tr><td>' + h(r.name || '-') + '</td><td class="mono">' + h(r.hash) + '</td><td>' + pol(r.policy, r.name || r.hash) + '</td></tr>');
  const look = '<div class="card"><h3>Model lookup</h3><div class="row"><input class="input" id="lookup-q" placeholder="Model name or hash" style="flex:1 1 auto" value="' + h(S.lookup || '') + '"><button class="btn primary" data-act="lookup">Look up</button></div>' +
    (lk ? '<div style="margin-top:14px">' + kv([['Query', lk.query], ['Hash', lk.hash], ['Name', lk.name || '(not in registry)'], ['Class', lk.class], ['Size', lk.size], ['Allowlisted', lk.allowed ? 'yes' : 'no'], ['Class policy', lk.policy]]) +
      '<div class="row" style="margin-top:12px"><span class="muted">Add a rule:</span>' + ['allow', 'block', 'ban'].map((o) => '<button class="btn small" data-act="entity-add" data-policy="' + o + '" data-model="' + h(lk.name || lk.hash) + '">' + o + '</button>').join('') + '</div></div>' : '') + '</div>';
  return head('Entity Rules', arr(c.entities).length, '', 'Per-model spawn policy: allow, block (cancel the spawn) or ban.') + look +
    '<div class="card"><div class="row" style="margin-bottom:12px">' + search('entities', 'Search rules...') + '</div>' + table(['Model', 'Hash', 'Policy'], trs, empty('No entity rules', 'Look a model up above to add one.'), ['auto', '160px', '160px']) + '</div>';
};

/* ================================================================== OBJECT LOG
   Every object spawned on the server (networked, judged by the entity guard)
   and every LOCAL object a client reported (invisible to the server otherwise).
   Each row can be whitelisted / blocked / ban-listed: the same Entity Rules as
   the Entity Rules page, saved on the server, applied to the next spawn. */
const OBJ_RES = { allowed: 'green', logged: 'faint', blocked: 'amber', banned: 'red', staff: 'blue' };
function objModelArg(r) { return r.named ? r.model : String(r.hash); }
function objRuleCell(r, canRule) {
  const cur = r.rule ? badge(r.rule === 'allow' ? 'whitelisted' : (r.rule === 'ban' ? 'ban-listed' : 'blocked'), r.rule === 'allow' ? 'green' : (r.rule === 'ban' ? 'red' : 'amber'))
    : (r.allowlisted ? badge('allowlist', 'faint') : '');
  if (!canRule) return cur || '<span class="muted">-</span>';
  const m = h(objModelArg(r));
  const b = (policy, label, cls) => (r.rule === policy ? '' : '<button class="btn small' + (cls ? ' ' + cls : '') + '" data-act="obj-rule" data-policy="' + policy + '" data-model="' + m + '" data-kind="' + h(r.kind || 'object') + '" data-label="' + h(r.model) + '">' + label + '</button>');
  return '<div class="row" style="gap:6px;flex-wrap:wrap">' + cur +
    b('allow', 'Whitelist', '') + b('block', 'Block', '') + b('ban', 'Ban-list', 'danger') +
    (r.rule ? '<button class="btn small" data-act="obj-rule" data-policy="remove" data-model="' + m + '" data-kind="' + h(r.kind || 'object') + '" data-label="' + h(r.model) + '">Clear</button>' : '') + '</div>';
}
PAGES.objects = () => {
  const d = S.data.objects;
  if (!d) return loading('Object Log');
  let rows = arr(d.rows);
  if (S.objNet !== 'all') rows = rows.filter((r) => (r.origin || (r.net ? 'client' : 'local')) === S.objNet);
  if (S.objKind !== 'all') rows = rows.filter((r) => (r.kind || 'object') === S.objKind);
  if (S.objRes !== 'all') rows = rows.filter((r) => r.action === S.objRes);
  rows = filterRows(rows, S.filters.objects, ['model', 'hashHex', 'hash', 'signed', 'player', 'src', 'script', 'why', 'class', 'kind']);
  const hits = d.hits || {};
  const ORIGIN = { client: ['player-made', 'blue'], local: ['local only', 'amber'], server: ['server script', 'green'] };
  const t = d.totals || {};
  const trs = rows.map((r) => '<tr>' +
    '<td class="muted" title="' + h(when(r.at)) + '">' + h(when(r.at).slice(6)) + '</td>' +
    '<td>' + (r.src > 0 ? '<a class="link" data-act="player" data-src="' + h(r.src) + '">[' + h(r.src) + '] ' + h(r.player) + '</a>' : '<span class="muted">' + h(r.player) + '</span>') + '</td>' +
    '<td class="wrapcell"><b class="mono">' + h(r.model) + '</b>' + (r.n > 1 ? ' <span class="badge">x' + h(r.n) + '</span>' : '') +
      '<br><small class="mono muted">' + h(r.hashHex) + ' &middot; ' + h(r.signed) + '</small></td>' +
    '<td>' + h(r.class || '-') + '<br><small class="muted">' + h(r.size || '?') + (r.extent ? ' &middot; ' + h(r.extent) + 'm' : '') + '</small></td>' +
    '<td>' + h(r.kind || 'object') + '<br>' + (function () { const o = ORIGIN[r.origin || (r.net ? 'client' : 'local')] || ['?', '']; return badge(o[0], o[1]); })() +
      (r.script ? '<br><small class="muted mono">' + h(r.script) + '</small>' : '') + '</td>' +
    '<td>' + badge(r.action, OBJ_RES[r.action] || '') + (r.why ? '<br><small class="muted">' + h(r.why) + '</small>' : '') + '</td>' +
    '<td>' + objRuleCell(r, d.canRule) + '</td></tr>');
  const tools = search('objects', 'Model, hash, player, script...') +
    sel('data-act-change="obj-kind"', [['all', 'All entities'], ['object', 'Objects'], ['vehicle', 'Vehicles'], ['ped', 'Peds']], S.objKind, '140px') +
    sel('data-act-change="obj-net"', [['all', 'Any origin'], ['client', 'Player-made'], ['local', 'Local only'], ['server', 'Server script']], S.objNet, '150px') +
    sel('data-act-change="obj-res"', [['all', 'Any result'], ['banned', 'Banned'], ['blocked', 'Blocked'], ['logged', 'Logged'], ['allowed', 'Allowed'], ['staff', 'Staff']], S.objRes, '140px');
  return head('Object Log', rows.length, '', 'Live. Every object, vehicle and ped spawned: exact model (spawn code) and hash, who, where it came from (a player, local only, or a server script), the script that made it, and what Nexus did. ' +
      'Whitelist = always allowed, Block = deleted on spawn, Ban-list = deleted + ban. Rules apply from the next spawn and are saved.') +
    '<div class="grid four">' +
      '<div class="card stat-card"><div class="k">Player-made / server</div><div class="v blue">' + h(num(t.net || 0)) + ' / ' + h(num(t.server || 0)) + '</div></div>' +
      '<div class="card stat-card"><div class="k">Local (client)</div><div class="v amber">' + h(num(t['local'] || 0)) + '</div></div>' +
      '<div class="card stat-card"><div class="k">Blocked</div><div class="v">' + h(num(t.blocked || 0)) + '</div></div>' +
      '<div class="card stat-card"><div class="k">Banned</div><div class="v red">' + h(num(t.banned || 0)) + '</div></div>' +
    '</div>' +
    '<div class="card"><div class="row" style="margin-bottom:12px;gap:8px;flex-wrap:wrap">' + tools + '</div>' +
    '<div class="muted" style="margin:-4px 0 10px;font-size:12px">Seen since NexusAC started: ' + h(num(hits.creating || 0)) + ' player creations, ' +
      h(num(hits.created || 0)) + ' entities created (' + h(num(hits.serverMade || 0)) + ' by server scripts), ' + h(num(hits.reports || 0)) + ' local reports from players.</div>' +
    table(['Time', 'Player', 'Model / spawn code', 'Class', 'Entity', 'Result', 'Rule'], trs,
      empty('Nothing yet', 'Objects, vehicles and peds show up here the moment they are spawned.'), ['80px', '15%', 'auto', '110px', '150px', '17%', '250px']) + '</div>';
};

/* ================================================================== CLEANUP / SECURITY / PERFORMANCE */
PAGES.cleanup = () => {
  const c = S.data.cleanup;
  if (!c) return loading();
  const cards = Object.keys(c).sort().map((cat) => '<div class="card stat-card"><div class="k" style="text-transform:capitalize">' + h(cat) + '</div><div class="v">' + h(num(c[cat])) + '</div><div class="s"><span>abandoned, not owned by a player</span></div>' +
    '<div class="row" style="margin-top:14px"><button class="btn small primary" data-act="clean" data-cat="' + h(cat) + '" data-scope="server" data-count="' + h(c[cat]) + '">Clean server</button>' +
    '<button class="btn small" data-act="clean" data-cat="' + h(cat) + '" data-scope="client" data-count="' + h(c[cat]) + '">Clean clients</button></div></div>').join('');
  return head('Cleanup', null, '<button class="btn primary" data-act="clean" data-cat="all" data-scope="server" data-count="0">Clean everything</button>', 'Props and peds go instantly (plus follow-up sweeps); empty vehicles after the countdown. Players, attached props, occupied vehicles and server-script entities are kept.') +
    '<div class="grid three">' + (cards || empty('Nothing to clean', '')) + '</div>';
};
function summaryCard(t, obj) {
  if (!obj) return '<div class="card"><h3>' + h(t) + '</h3>' + empty('No report yet', 'Run a scan.') + '</div>';
  const pairs = scalars(obj);
  const lists = Object.keys(obj).filter((k) => Array.isArray(obj[k]) && obj[k].length).map((k) =>
    '<section style="margin-top:12px"><h4 class="dim" style="margin:0 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.08em">' + h(k) + ' (' + obj[k].length + ')</h4><pre class="json">' + h(pretty(obj[k].slice(0, 40))) + '</pre></section>').join('');
  return '<div class="card"><h3>' + h(t) + '</h3>' + (pairs.length ? kv(pairs) : '') + lists + '</div>';
}
PAGES.security = () => {
  const d = S.data.security;
  if (!d) return loading();
  return head('Security', null, '<button class="btn primary" data-act="scan" data-op="resources">Scan resources</button>', 'Resource event audit and server hardening.') +
    summaryCard('Hardening', d.hardening) + summaryCard('Resource scan', d.scan);
};
PAGES.performance = () => {
  const d = S.data.profile;
  if (!d) return loading();
  if (!d.available) return head('Performance') + '<div class="card">' + empty('Profiler unavailable', 'Config.Performance.profiler is off.') + '</div>';
  const trs = arr(d.rows).map((r) => '<tr><td class="mono wrapcell">' + h(r.label) + '</td><td>' + h(num(r.calls)) + '</td><td>' + h(num(r.totalMs, 2)) + '</td><td>' + h(num(r.avgUs, 1)) +
    '</td><td>' + h(num(r.maxMs, 2)) + '</td><td><b>' + h(num(r.msPerSec, 3)) + '</b></td></tr>');
  const tools = badge(d.on ? 'recording' : 'stopped', d.on ? 'green' : 'faint') +
    (d.on ? '<button class="btn" data-act="prof" data-op="stop">Stop</button>' : '<button class="btn primary" data-act="prof" data-op="start">Start (5 min)</button>') +
    '<button class="btn" data-act="prof" data-op="reset">Reset</button>';
  return head('Performance', null, tools, 'Server CPU per NexusAC handler and thread. ' + num(d.elapsed, 0) + 's recorded, ' + num(d.sum, 2) + ' ms total = ' + num(d.elapsed > 0 ? d.sum / d.elapsed : 0, 3) + ' ms per second.') +
    '<div class="card" style="padding:8px 10px">' + table(['Handler / thread', 'Calls', 'Total ms', 'Avg us', 'Max ms', 'ms/s'], trs, empty('Nothing recorded', 'Start the profiler, play for a few minutes, then read this.'), ['auto', '80px', '90px', '90px', '90px', '90px']) + '</div>';
};

/* ================================================================== INVENTORIES */
/* Item pictures come straight from ox_inventory (nui://ox_inventory/web/images).
   A missing image falls back through metadata.image, the exact name, its
   lower/upper-case forms, then initials -- never a broken-image icon. */
const OX_IMG = 'nui://ox_inventory/web/images/';
function imgCandidates(it) {
  const m = it.metadata || {};
  const list = [];
  if (m.imageurl) list.push(m.imageurl);
  if (m.image) list.push(OX_IMG + m.image + (/\.(png|webp|jpg)$/i.test(m.image) ? '' : '.png'));
  [it.name, String(it.name || '').toLowerCase(), String(it.name || '').toUpperCase()].forEach((n) => { const u = OX_IMG + n + '.png'; if (n && !list.includes(u)) list.push(u); });
  return list;
}
function initials(it) {
  const t = String(it.label || it.name || '?').replace(/^weapon_/i, '');
  return t.split(/[\s_]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
}
function itemPic(it) { const c = imgCandidates(it); return '<img src="' + h(c[0]) + '" data-fallbacks="' + h(c.slice(1).join('|')) + '" data-initials="' + h(initials(it)) + '" alt="">'; }
document.addEventListener('error', (ev) => {
  const img = ev.target;
  if (!img || img.tagName !== 'IMG' || !img.hasAttribute('data-initials')) return;
  const rest = (img.getAttribute('data-fallbacks') || '').split('|').filter(Boolean);
  if (rest.length) { img.setAttribute('data-fallbacks', rest.slice(1).join('|')); img.src = rest[0]; }
  else { const ph = document.createElement('div'); ph.className = 'ph'; ph.textContent = img.getAttribute('data-initials'); img.parentNode.replaceChild(ph, img); }
}, true);
function itemsGrid(items, where) {
  const list = arr(items);
  if (!list.length) return '<div class="card">' + empty('Empty', '') + '</div>';
  return '<div class="inv-grid">' + list.map((it, i) => {
    const key = where + ':' + i;
    S.items[key] = it;
    const m = it.metadata || {};
    const dura = m.durability != null ? Math.max(0, Math.min(100, Number(m.durability))) : null;
    const sub = m.serial ? m.serial : (m.registered ? m.registered : (m.ammo != null ? 'ammo ' + m.ammo : ''));
    return '<button class="inv-tile' + (it.weapon ? ' weapon' : '') + '" data-act="item" data-key="' + h(key) + '" title="' + h((it.label || it.name) + (m.serial ? ' · ' + m.serial : '')) + '">' +
      '<span class="count">' + h(num(it.count)) + 'x</span>' + (it.slot != null ? '<span class="slot">' + h(it.slot) + '</span>' : '') +
      '<div class="pic">' + itemPic(it) + '</div><div class="name">' + h(it.label || it.name) + '</div>' + (sub ? '<div class="sub">' + h(sub) + '</div>' : '') +
      (dura != null && isFinite(dura) ? '<div class="bar"><i style="width:' + dura + '%"></i></div>' : '') + '</button>';
  }).join('') + '</div>';
}
function invSection(t, items, where) {
  const list = arr(items);
  const total = list.reduce((n, it) => n + (Number(it.count) || 0), 0);
  return '<div class="inv-head"><h4>' + h(t) + '</h4><span>' + list.length + ' slots · ' + num(total) + ' items</span></div>' + itemsGrid(list, where);
}
function itemModal(it) {
  const m = it.metadata || {};
  const comps = Array.isArray(m.components) ? m.components : [];
  const rest = scalars(m, ['serial', 'registered', 'ammo', 'durability', 'components', 'image', 'imageurl', 'label']);
  modal('<div class="item-view"><div class="big">' + itemPic(it) + '</div><div class="about"><h2>' + h(it.label || it.name) + '</h2><p class="mono">' + h(it.name) + '</p>' +
    kv([['Count', num(it.count)], ['Slot', it.slot], ['Serial', m.serial], ['Registered to', m.registered], ['Ammo', m.ammo],
      ['Durability', m.durability != null ? num(m.durability, 0) + '%' : null], ['Attachments', comps.length ? comps.join(', ') : null]].concat(rest)) +
    '</div></div><div class="foot">' + (m.serial ? '<button class="btn" data-m="trace">Trace serial</button>' : '') + '<button class="btn primary" data-m="close">Close</button></div>',
  (n) => {
    n.classList.add('wide');
    n.querySelector('[data-m=close]').onclick = closeModal;
    const tr = n.querySelector('[data-m=trace]');
    if (tr) tr.onclick = () => { closeModal(); S.serialId = m.serial; openDrawer('serial'); request('serial', m.serial); };
  });
}
PAGES.inventories = () => {
  const d = S.data.inventories;
  if (!d) return loading();
  if (d.ready === false) return head('Inventories') + '<div class="card">' + empty('Database unavailable', 'oxmysql is not running, so saved inventories cannot be read.') + '</div>';
  const trs = arr(d.rows).map((r) => '<tr class="click" data-act="inv" data-id="' + h(r.identifier) + '"><td>' + (r.online ? badge('online', 'green') : badge('offline', 'faint')) +
    '</td><td><b>' + h(r.name || '(no name)') + '</b></td><td>' + h(r.player ? r.player + ' (#' + r.src + ')' : '-') + '</td><td>' + h(r.job || '-') + (r.job_grade != null ? ' ' + h(r.job_grade) : '') +
    '</td><td class="mono wrapcell dim">' + h(r.identifier) + '</td><td class="right"><button class="btn small" data-act="inv" data-id="' + h(r.identifier) + '">Open</button></td></tr>');
  return head('Inventories', arr(d.rows).length, '', 'Every character, online or offline. Online players are read live; offline ones from their last save.') +
    '<div class="bar-card">' + search('inventories', 'Search character, identifier or player name...') + '</div><div style="height:18px"></div>' +
    '<div class="card" style="padding:8px 10px">' + table(['', 'Character', 'Player', 'Job', 'Identifier', ''], trs, empty('No characters match', ''), ['90px', '22%', '20%', '120px', 'auto', '90px']) + '</div>';
};
DRAWERS.inv = () => {
  const d = S.data.inventory && S.data.inventory.identifier === S.invId ? S.data.inventory : null;
  if (!d) return drawerShell('Inventory', empty('Loading inventory', ''));
  S.items = {};
  const acc = d.accounts && typeof d.accounts === 'object' ? d.accounts : {};
  const items = arr(d.items);
  const weapons = items.filter((it) => it.weapon).length;
  const card = (k, v) => '<div class="card"><div class="k">' + h(k) + '</div><div class="v">' + h(v) + '</div></div>';
  const summary = '<div class="inv-summary">' + card('Cash', '$' + num(acc.money || 0)) + card('Bank', '$' + num(acc.bank || 0)) +
    card('Dirty money', '$' + num(acc.black_money || 0)) + card('Items', items.length + ' slots · ' + weapons + ' weapons') + '</div>';
  const actions = '<div class="row" style="margin-bottom:10px">' + badge(d.online ? (d.live ? 'online · live inventory' : 'online') : 'offline · last saved', d.online ? 'green' : 'faint') +
    '<span class="spacer"></span>' + (d.online && can('config') ? '<button class="btn primary" data-act="ox-open" data-src="' + h(d.src) + '">Open in ox_inventory</button>' : '') + '</div>';
  const info = kv([['Player', d.player ? d.player + ' (#' + d.src + ')' : null], ['Identifier', d.identifier], ['Job', d.job ? d.job + ' ' + (d.grade == null ? '' : d.grade) : null], ['Group', d.group]]);
  let extra = '';
  arr(d.vehicles).forEach((v, vi) => {
    if (arr(v.glovebox).length) extra += invSection('Vehicle ' + v.plate + ' · glovebox', v.glovebox, 'g' + vi);
    if (arr(v.trunk).length) extra += invSection('Vehicle ' + v.plate + ' · trunk', v.trunk, 't' + vi);
  });
  arr(d.stashes).forEach((st, si) => { if (arr(st.items).length) extra += invSection('Stash ' + st.name, st.items, 's' + si); });
  return drawerShell(d.name || d.identifier, actions + summary + '<div class="card">' + info + '</div>' + invSection('Inventory', items, 'inv') + extra);
};
DRAWERS.serial = () => {
  const d = S.data.serial && S.data.serial.serial === S.serialId ? S.data.serial : null;
  if (!d) return drawerShell('Serial ' + (S.serialId || ''), empty('Tracing serial', ''));
  const holders = arr(d.holders).map((x) => '<tr><td>' + h(x.where) + '</td><td class="wrapcell">' + h(x.holder || '-') + (x.src ? ' (#' + h(x.src) + ')' : '') + '</td><td class="mono wrapcell dim">' + h(x.identifier || '') + '</td></tr>');
  return drawerShell('Serial ' + d.serial, '<section><h4>Where it is now</h4>' + table(['Where', 'Holder', 'Identifier'], holders, empty('Not found anywhere', 'Dropped, destroyed or never saved.'), ['30%', '35%', 'auto']) + '</section>');
};

/* ================================================================== events */
function switchMode() {
  const cur = (S.data.overview && S.data.overview.mode) || S.info.mode;
  const mode = cur === 'enforce' ? 'observe' : 'enforce';
  if (!can('config')) return toast(false, 'Your role cannot change the mode.');
  confirmAction({ title: 'Switch to ' + mode, reason: false, danger: mode === 'enforce', ok: 'Switch',
    text: mode === 'enforce' ? 'Detectors in enforce mode will kick and ban again.' : 'Nothing will be kicked or banned; findings are recorded only.',
    onOk: () => exec({ type: 'mode', mode, expected: cur }) });
}
function protChange(p, change) {
  const exp = protExpected(p);
  exec(Object.assign({ type: 'protection', id: p.id, expected: exp }, exp, change));
}

document.addEventListener('click', (ev) => {
  const el = ev.target.closest('[data-tab], [data-act]');
  if (!el) return;
  if (el.hasAttribute('data-tab')) { setTab(el.getAttribute('data-tab')); return; }
  const act = el.getAttribute('data-act');
  const src = el.getAttribute('data-src');
  const id = el.getAttribute('data-id');
  switch (act) {
    case 'nav-group': { const g = el.getAttribute('data-group'); S.navOpen[g] = !S.navOpen[g]; savePrefs(); renderNav(); break; }
    case 'drawer-close': closeDrawer(); break;
    case 'refresh': refreshTab(true); break;
    case 'mode-toggle': switchMode(); break;
    case 'staff-only': S.staffOnly = !S.staffOnly; render(true); break;
    case 'inv': S.invId = id; openDrawer('inv'); request('inventory', id); break;
    case 'item': { const it = S.items[el.getAttribute('data-key')]; if (it) itemModal(it); break; }
    case 'ox-open': exec({ type: 'oxopen', target: Number(src) }); closePanel(); break;
    case 'player': S.playerSrc = src; openDrawer('player'); request('player', Number(src)); if (!S.data.players) request('players'); break;
    case 'p-spectate': playerCmd('spectate'); break;
    case 'p-screen': { const p = playerRow(S.playerSrc); if (p) { exec({ type: 'nexwatch', target: p.src }); setTab('spectate'); } break; }
    case 'p-shot': confirmAction({ title: 'Take a screenshot', text: 'Captured as evidence.', ok: 'Capture', onOk: (r) => playerCmd('screenshot', { reason: r }) }); break;
    case 'p-freeze': {
      const p = playerRow(S.playerSrc);
      const on = !(p && p.frozen);
      confirmAction({ title: on ? 'Freeze player' : 'Unfreeze player', ok: on ? 'Freeze' : 'Unfreeze', onOk: (r) => playerCmd('freeze', { on, reason: r }) });
      break;
    }
    case 'p-warn': confirmAction({ title: 'Warn player', text: 'Recorded against their identity and shown to them.', ok: 'Warn', onOk: (r) => playerCmd('warn', { reason: r }) }); break;
    case 'p-kick': confirmAction({ title: 'Kick player', danger: true, ok: 'Kick', onOk: (r) => playerCmd('kick', { reason: r }) }); break;
    case 'p-ban': banModal(); break;
    case 'd-cmd': {
      S.playerSrc = src;
      const cmd = el.getAttribute('data-cmd');
      if (cmd === 'spectate') playerCmd('spectate');
      else if (cmd === 'screenshot') confirmAction({ title: 'Take a screenshot', text: 'Captured as evidence.', ok: 'Capture', onOk: (r) => playerCmd('screenshot', { reason: r }) });
      else if (cmd === 'kick') confirmAction({ title: 'Kick player', danger: true, ok: 'Kick', onOk: (r) => playerCmd('kick', { reason: r }) });
      else if (cmd === 'ban') banModal();
      break;
    }
    case 'det': {
      const r = feedRow(id, el.getAttribute('data-at'), src);
      if (!r) break;
      S.detId = r;
      openDrawer('det');
      request('bans');
      if (can('view_evidence') && r.name) request('evidence', r.name);
      if (!S.data.players) request('players');
      break;
    }
    case 'nex-watch': exec({ type: 'nexwatch', target: Number(src) }); setTimeout(() => request('nex'), 400); break;
    case 'nex-stop': exec({ type: 'nexstop', target: Number(src) }); delete S.nexFrames[src]; setTimeout(() => request('nex'), 400); break;
    case 'nex-reset': arr(S.data.nex && S.data.nex.watching).forEach((w) => { exec({ type: 'nexstop', target: Number(w.src) }); delete S.nexFrames[w.src]; }); setTimeout(() => request('nex'), 400); break;
    case 'sp-layout': S.spLayout = Number(el.getAttribute('data-n')) || 3; savePrefs(); render(true); break;
    case 'sp-filter': S.spFilter = el.getAttribute('data-f'); render(true); break;
    case 'prot-tab': S.protTab = el.getAttribute('data-t'); render(true); request(S.protTab === 'detections' ? 'protections' : 'config'); if (S.protTab === 'lists') request('lists'); break;
    case 'prot': S.protId = id; delete S.drafts['prot:' + id]; openDrawer('prot'); if (!protRow(id)) request('protections'); break;
    case 'prot-toggle': { const p = protRow(id); if (p) protChange(p, { enabled: !p.enabled }); break; }
    case 'pd-toggle': {
      const p = protRow(S.protId);
      if (!p) break;
      const key = el.getAttribute('data-key');
      const d = S.drafts['prot:' + p.id] || protExpected(p);
      d[key] = !d[key];
      S.drafts['prot:' + p.id] = d;
      renderDrawer();
      break;
    }
    case 'pd-reset': delete S.drafts['prot:' + S.protId]; renderDrawer(); break;
    case 'pd-save': {
      const p = protRow(S.protId);
      if (!p) break;
      const d = S.drafts['prot:' + p.id] || protExpected(p);
      exec(Object.assign({ type: 'protection', id: p.id, expected: protExpected(p) }, d, { minConfidence: Math.floor(Number(d.minConfidence) || 85) }));
      delete S.drafts['prot:' + p.id];
      break;
    }
    case 'ev': S.evidenceId = id; openDrawer('ev'); request('evidenceItem', id); break;
    case 'ban-shots': S.banShotId = id; S.banShotSel = null; openDrawer('banshots'); request('banShots', id); break;
    case 'wl-add-online': {
      const sel = $('wl-online');
      if (!sel || !sel.value) break;
      exec({ type: 'whitelist', op: 'add', target: Number(sel.value), name: '', note: ($('wl-note') || {}).value || '' });
      setTimeout(() => request('whitelist'), 500);
      break;
    }
    case 'wl-add-id': {
      const key = (($('wl-key') || {}).value || '').trim();
      if (!/^[A-Za-z0-9]+:[A-Za-z0-9_-]+$/.test(key) || /^ip:/i.test(key)) { toast(false, 'Type an identifier like license:abc123 or discord:1234567890.'); break; }
      exec({ type: 'whitelist', op: 'add', key, name: (($('wl-name') || {}).value || '').trim(), note: (($('wl-note2') || {}).value || '').trim() });
      setTimeout(() => request('whitelist'), 500);
      break;
    }
    case 'wl-remove': confirmAction({ title: 'Remove ' + (el.getAttribute('data-name') || id) + ' from the whitelist', text: 'NexusAC will judge them like every other player again.', ok: 'Remove', reason: false,
      onOk: () => { exec({ type: 'whitelist', op: 'remove', key: id }); setTimeout(() => request('whitelist'), 500); } }); break;
    case 'bs-pick': S.banShotSel = Number(el.getAttribute('data-i')); renderDrawer(); break;
    case 'bs-full': {
      const d = S.data.banShots;
      const f = d && arr(d.frames)[Number(el.getAttribute('data-i'))];
      if (f) modal('<img class="bs-fullimg" src="' + h(f.data) + '"><div class="foot"><span class="muted">' + h(bsLabel(f, d)) + '</span><span class="spacer"></span><button class="btn" data-m="cancel">Close</button></div>',
        (node) => { node.classList.add('wide'); node.querySelector('[data-m=cancel]').onclick = closeModal; });
      break;
    }
    case 'unban': confirmAction({ title: 'Unban ' + (el.getAttribute('data-name') || id), text: 'Lifts every identifier on this ban.', ok: 'Unban',
      onOk: (r) => { exec({ type: 'unban', banId: id, reason: r }); setTimeout(() => request('bans'), 500); } }); break;
    case 'ban-clear': S.filters.bans = ''; S.banStatus = 'all'; render(true); break;
    case 'sig-show': S.sigChanged = el.getAttribute('data-v') === 'changed'; render(true); break;
    case 'set-group': S.settingsGroup = el.getAttribute('data-group'); S.filters.settings = ''; render(true); break;
    case 'set-bool': {
      const path = el.getAttribute('data-path');
      const s = S.data.config && S.data.config.settings[path];
      if (!s) break;
      if (path === 'general.adminWhitelist' && s.value) {
        confirmAction({ title: 'Turn the admin whitelist off', reason: false, danger: true, ok: 'Turn off',
          text: 'Staff will be detected like normal players. If you use a cheat now, NexusAC WILL isolate and ban you.',
          onOk: () => exec({ type: 'setting', path, value: false, expected: true }) });
      } else exec({ type: 'setting', path, value: !s.value, expected: s.value });
      break;
    }
    case 'set-save': {
      const path = el.getAttribute('data-path');
      const s = S.data.config && S.data.config.settings[path];
      const key = 'set:' + path;
      if (!s || !Object.prototype.hasOwnProperty.call(S.drafts, key)) break;
      let v = S.drafts[key];
      if (s.kind === 'number') {
        v = Number(v);
        if (!isFinite(v)) { toast(false, 'That is not a number.'); break; }
        if ((s.lo != null && v < s.lo) || (s.hi != null && v > s.hi)) { toast(false, 'Out of range (' + s.lo + ' to ' + s.hi + ').'); break; }
      }
      exec({ type: 'setting', path, value: v, expected: s.value });
      delete S.drafts[key];
      break;
    }
    case 'wh-save': case 'wh-clear': {
      const cat = el.getAttribute('data-cat');
      const input = $('wh-' + cat);
      const url = act === 'wh-clear' ? '' : (input ? input.value.trim() : '');
      if (act === 'wh-save' && !/^https:\/\/(discord\.com|discordapp\.com|ptb\.discord\.com|canary\.discord\.com)\/api\/webhooks\//.test(url)) {
        toast(false, 'Paste a Discord webhook URL (https://discord.com/api/webhooks/...).'); break;
      }
      exec({ type: 'webhook', category: cat, url });
      if (input) input.value = '';
      break;
    }
    case 'ev-add': eventRuleModal(null); break;
    case 'ev-edit': eventRuleModal(arr(S.data.eventRules && S.data.eventRules.rules).find((r) => r.name === el.getAttribute('data-name'))); break;
    case 'ev-del': { const name = el.getAttribute('data-name'); confirmAction({ title: 'Delete ' + name, reason: false, danger: true, ok: 'Delete', onOk: () => exec({ type: 'eventRule', operation: 'delete', name }) }); break; }
    case 'ev-export': {
      const lines = arr(S.data.eventRules && S.data.eventRules.rules).map((r) => r.name + ' ' + r.mode + (r.mode === 'watch' ? ' ' + (r.perMinute || '') : '')).join('\n');
      modal('<h2>Export event rules</h2><p>One rule per line: name, mode, rate. Select all and copy.</p><textarea class="textarea mono" style="min-height:260px" readonly>' + h(lines) + '</textarea>' +
        '<div class="foot"><button class="btn primary" data-m="close">Close</button></div>', (n) => { n.querySelector('[data-m=close]').onclick = closeModal; });
      break;
    }
    case 'ev-import':
      modal('<h2>Import event rules</h2><p>One per line: <span class="mono">event:name watch 60</span> or <span class="mono">event:name ignore</span>. Up to 128.</p>' +
        '<textarea class="textarea mono" id="ev-import-text" style="min-height:220px"></textarea><div id="m-error" class="muted" style="margin-top:8px"></div>' +
        '<div class="foot"><button class="btn" data-m="cancel">Cancel</button><button class="btn primary" data-m="ok">Import</button></div>', (n) => {
        n.querySelector('[data-m=cancel]').onclick = closeModal;
        n.querySelector('[data-m=ok]').onclick = () => {
          const rules = [], bad = [];
          n.querySelector('#ev-import-text').value.split(/\r?\n/).forEach((line, i) => {
            const parts = line.trim().split(/[\s,;]+/).filter(Boolean);
            if (!parts.length) return;
            const mode = (parts[1] || 'watch').toLowerCase();
            if (mode !== 'watch' && mode !== 'ignore') { bad.push(i + 1); return; }
            const rule = { name: parts[0], mode };
            if (mode === 'watch') rule.perMinute = Math.floor(Number(parts[2] || 60));
            rules.push(rule);
          });
          if (bad.length) { n.querySelector('#m-error').textContent = 'Lines ' + bad.join(', ') + ' need mode watch or ignore.'; return; }
          if (!rules.length) { n.querySelector('#m-error').textContent = 'Nothing to import.'; return; }
          closeModal();
          exec({ type: 'eventRule', operation: 'import', rules });
        };
      });
      break;
    case 'lookup': { const q = ($('lookup-q') || {}).value || ''; if (q.trim()) { S.lookup = q.trim(); request('lookup', S.lookup); } break; }
    case 'entity-add': exec({ type: 'entity', model: el.getAttribute('data-model'), policy: el.getAttribute('data-policy') }); break;
    case 'obj-rule': {
      const model = el.getAttribute('data-model'), policy = el.getAttribute('data-policy'), label = el.getAttribute('data-label') || model;
      const what = { allow: 'Whitelist', block: 'Block', ban: 'Ban-list', remove: 'Clear the rule for' }[policy] || policy;
      const text = { allow: 'It will always be allowed to spawn, by anyone.', block: 'It will be deleted the moment anyone spawns it (no ban).',
        ban: 'Anyone who spawns it is banned on the spot and it is deleted.', remove: 'It goes back to the normal rules for its type.' }[policy] || '';
      confirmAction({ title: what + ' ' + label, text, reason: false, danger: policy === 'ban', ok: what,
        onOk: () => exec({ type: 'entity', model, policy, kind: el.getAttribute('data-kind') || 'object' }) });
      break;
    }
    case 'list-add': listAdd(el.getAttribute('data-key')); break;
    case 'list-remove': {
      const model = el.getAttribute('data-model'), key = el.getAttribute('data-key'), from = el.getAttribute('data-from');
      const L = LISTS.find((x) => x.key === key);
      const own = from === 'yours';
      let policy = 'remove', text = 'It goes back to the normal rules for its type.';
      if (!own && L && L.policy === 'ban') { policy = 'allow'; text = 'This is a default entry, so it moves to the whitelist: spawning it will no longer ban.'; }
      if (!own && L && L.policy === 'allow') { policy = 'block'; text = 'This is a default entry, so it will be removed when spawned (no ban).'; }
      confirmAction({ title: 'Remove ' + (el.getAttribute('data-name') || model), reason: false, ok: 'Remove', text,
        onOk: () => { exec({ type: 'entity', model, policy, kind: L ? L.kind : undefined }); setTimeout(() => { request('config'); request('lists'); }, 400); } });
      break;
    }
    case 'clean': {
      const cat = el.getAttribute('data-cat'), scope = el.getAttribute('data-scope'), count = Number(el.getAttribute('data-count'));
      confirmAction({ title: 'Clean ' + cat + ' (' + scope + ')', reason: false, danger: true, ok: 'Clean',
        text: scope === 'server' ? (cat === 'all' ? 'Deletes every abandoned prop, ped and empty vehicle, on the server and on every client.' : 'Deletes ~' + count + ' abandoned ' + cat + ' (server + every client).') : 'Asks every client to clear local ' + cat + '.',
        onOk: () => exec({ type: 'cleanup', category: cat, scope, expected: count }) });
      break;
    }
    case 'scan': exec({ type: 'scan', op: el.getAttribute('data-op') }); break;
    case 'res-op': {
      const name = el.getAttribute('data-name'), op = el.getAttribute('data-op');
      const go = () => { exec({ type: 'resource', name, op }); setTimeout(() => request('resources'), 700); };
      if (op === 'start') { go(); break; }
      confirmAction({ title: (op === 'stop' ? 'Stop ' : 'Restart ') + name, reason: false, danger: op === 'stop', ok: op === 'stop' ? 'Stop' : 'Restart',
        text: op === 'stop' ? 'Everything this resource does stops for every player until it is started again.'
                            : 'The resource stops and starts again. Players may notice a short interruption.',
        onOk: go });
      break;
    }
    case 'prof': exec({ type: 'profile', op: el.getAttribute('data-op'), seconds: 300 }); break;
    default: break;
  }
});
function banModal() {
  confirmAction({ title: 'Ban player', danger: true, ok: 'Ban',
    extra: '<label class="field" style="margin-bottom:12px"><span>Duration</span><select class="select" data-mv="days"><option value="1">1 day</option><option value="3">3 days</option><option value="7">7 days</option><option value="14">14 days</option><option value="30" selected>30 days</option><option value="0">Permanent</option></select></label>',
    onOk: (r, v) => playerCmd('ban', { reason: r, days: Math.floor(Number(v.days) || 0) }) });
}

document.addEventListener('input', (ev) => {
  const el = ev.target;
  if (el.hasAttribute('data-filter')) {
    const key = el.getAttribute('data-filter');
    S.filters[key] = el.value;
    if (key === 'inventories' || key === 'evidence') {
      clearTimeout(S.searchTimer);
      S.searchTimer = setTimeout(() => refreshTab(), 350);
      return;
    }
    render(true);
    return;
  }
  if (el.hasAttribute('data-list')) { S.drafts['list:' + el.getAttribute('data-list')] = el.value; return; }
  if (el.hasAttribute('data-set')) {
    S.drafts['set:' + el.getAttribute('data-set')] = el.value;
    const btn = el.parentNode.querySelector('[data-act=set-save]');
    if (btn) { btn.disabled = false; btn.classList.add('primary'); }
    return;
  }
  if (el.hasAttribute('data-pd')) {
    const p = protRow(S.protId);
    if (!p) return;
    const d = S.drafts['prot:' + p.id] || protExpected(p);
    const key = el.getAttribute('data-pd');
    d[key] = key === 'minConfidence' ? Number(el.value) : el.value;
    S.drafts['prot:' + p.id] = d;
    if (key === 'minConfidence' && $('pd-conf')) $('pd-conf').textContent = el.value + '%';
  }
});

document.addEventListener('change', (ev) => {
  const el = ev.target;
  const act = el.getAttribute('data-act-change');
  if (act === 'punish') {
    const kind = el.getAttribute('data-kind');
    exec({ type: 'punish', signal: kind, action: el.value, expected: el.getAttribute('data-expected') });
    // 2026-10-11: update our own copy at once, so the NEXT change sends the
    // right "expected" value (it used to be refused until the next refresh).
    el.setAttribute('data-expected', el.value);
    const c = S.data.config;
    const row = c && arr(c.kinds).find((k) => k.kind === kind);
    if (row) row.action = el.value;
    if (c && c.punish) { if (el.value === 'risk') delete c.punish[kind]; else c.punish[kind] = el.value; }
    setTimeout(() => request('config'), 1500);
  }
  else if (act === 'entity') exec({ type: 'entity', model: el.getAttribute('data-model'), policy: el.value, expected: el.getAttribute('data-expected') });
  else if (act === 'prot-action') { const p = protRow(el.getAttribute('data-id')); if (p) protChange(p, { action: el.value }); }
  else if (act === 'prot-cat') { S.protCat = el.value; render(true); }
  else if (act === 'det-sev') { S.detSev = el.value; render(true); }
  else if (act === 'ban-view') { S.banView = el.value; savePrefs(); render(true); }
  else if (act === 'ban-status') { S.banStatus = el.value; render(true); }
  else if (act === 'audit-kind') { S.auditKind = el.value; render(true); }
  else if (act === 'res-state') { S.resState = el.value; render(true); }
  else if (act === 'obj-net') { S.objNet = el.value; render(true); }
  else if (act === 'obj-kind') { S.objKind = el.value; render(true); }
  else if (act === 'obj-res') { S.objRes = el.value; render(true); }
  else if (el.hasAttribute('data-pmode')) {
    const p = protRow(S.protId);
    if (p && el.value !== (p.mode || 'enforce')) exec({ type: 'detector', detector: p.id, mode: el.value, expected: p.mode || 'enforce' });
  } else if (el.hasAttribute('data-pd')) {
    const p = protRow(S.protId);
    if (!p) return;
    const d = S.drafts['prot:' + p.id] || protExpected(p);
    d[el.getAttribute('data-pd')] = el.getAttribute('data-pd') === 'minConfidence' ? Number(el.value) : el.value;
    S.drafts['prot:' + p.id] = d;
  }
});

document.addEventListener('keydown', (ev) => {
  const el = ev.target;
  if (ev.key === 'Enter' && el && el.hasAttribute && el.hasAttribute('data-list')) { ev.preventDefault(); listAdd(el.getAttribute('data-list')); }
});

// Never redraw between mouse-down and mouse-up: a redraw there swapped the
// button out from under the click, so Add (and other buttons next to a text
// box) did nothing.
let mouseDown = false;
document.addEventListener('mousedown', () => { mouseDown = true; }, true);
document.addEventListener('mouseup', () => {
  mouseDown = false;
  setTimeout(() => { if (S.pendingRender && !isTyping()) render(); }, 60);
}, true);
document.addEventListener('focusout', () => { setTimeout(() => { if (S.pendingRender && !isTyping() && !mouseDown) render(); }, 0); });
document.addEventListener('keydown', (ev) => {
  if (!S.open) return;
  if (ev.key === 'Escape') {
    ev.preventDefault();
    if (S.modal) closeModal();
    else if (S.drawer) closeDrawer();
    else closePanel();
  }
});

$('btn-close-side').innerHTML = I('x', 'sm');
$('btn-refresh').innerHTML = I('refresh', 'sm');
$('btn-mode').innerHTML = I('power', 'sm');
$('btn-close-side').addEventListener('click', () => closePanel());
$('btn-refresh').addEventListener('click', () => { refreshTab(true); toast(true, 'Refreshing.'); });
$('btn-mode').addEventListener('click', () => switchMode());

/* ================================================================== lifecycle */
let pollTimer = null;
const lastPoll = {};
function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    if (!S.open || document.hidden) return;
    const t = tabOf(S.tab);
    const now = Date.now();
    // The nav counts and the sidebar slots stay fresh on every page.
    if (now - (lastPoll._bg || 0) > 10000) {
      lastPoll._bg = now;
      if (can('view_players') && S.tab !== 'players') request('players');
      if (can('view') && S.tab !== 'detections') request('feed');
      if (can('view') && S.tab !== 'dashboard') request('overview');
    }
    if (!t || !t.poll) return;
    // Signal actions only change from this page: no full-config poll there.
    if (t.id === 'protection' && S.protTab === 'signals') return;
    if (now - (lastPoll[t.id] || 0) < t.poll) return;
    lastPoll[t.id] = now;
    refreshTab();
  }, 500);
}
function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }

function openPanel(info) {
  S.open = true;
  post('opened', {});
  S.info = info || {};
  S.caps = (info && info.caps) || {};
  $('server-name').textContent = S.info.server || 'Server';
  $('me-role').textContent = S.info.role || 'staff';
  $('version').textContent = S.info.version ? 'v' + S.info.version : '';
  const t = tabOf(S.tab);
  if (!t || !can(t.cap)) S.tab = (TABS.find((x) => can(x.cap)) || TABS[0]).id;
  $('app').classList.remove('hidden');
  renderChrome();
  renderNav();
  render(true);
  refreshTab();
  if (can('view_players') && S.tab !== 'players') request('players');
  if (can('view') && S.tab !== 'dashboard') request('overview');
  if (can('view') && S.tab !== 'detections') request('feed');
  startPolling();
}
function closePanel() {
  if (!S.open) return;
  S.open = false;
  stopPolling();
  closeModal();
  closeDrawer();
  $('app').classList.add('hidden');
  post('close', {});
}

window.addEventListener('message', (ev) => {
  const m = ev.data || {};
  if (m.type === 'open') { openPanel(m.data); return; }
  if (m.type === 'close') {
    if (S.open) { S.open = false; stopPolling(); closeModal(); closeDrawer(); $('app').classList.add('hidden'); }
    return;
  }
  if (!S.open) return;
  if (m.type === 'section') {
    if (m.denied) { toast(false, 'Your role cannot view ' + m.section + '.'); return; }
    if (m.error) { toast(false, 'The server could not build ' + m.section + '.'); return; }
    S.data[m.section] = m.data;
    if (m.section === 'overview' && m.data && m.data.you) {
      const you = arr(S.data.players).find((p) => String(p.src) === String(m.data.you.src));
      $('me-name').textContent = m.data.you.name || 'staff';
      $('me-avatar').textContent = initialsOf(m.data.you.name);
      void you;
    }
    if (m.section === 'overview' || m.section === 'players') renderChrome();
    if (m.section === 'players' || m.section === 'feed') renderNav();
    if (m.section === 'feed' && S.drawer === 'det' && S.detId) {
      const fresh = feedRow(S.detId.id, S.detId.at, S.detId.src);
      if (fresh) S.detId = fresh;
    }
    const t = tabOf(S.tab);
    const mine = t && (t.section === m.section || (t.also || []).includes(m.section) || (S.tab === 'entities' && m.section === 'lookup') || (S.tab === 'protection' && m.section === 'lists'));
    if (mine) render();
    if ((m.section === 'player' && S.drawer === 'player') || (m.section === 'evidenceItem' && S.drawer === 'ev') || (m.section === 'banShots' && S.drawer === 'banshots') ||
        (m.section === 'players' && (S.drawer === 'player' || S.drawer === 'det')) || (m.section === 'protections' && S.drawer === 'prot') ||
        (m.section === 'inventory' && S.drawer === 'inv') || (m.section === 'serial' && S.drawer === 'serial') ||
        (S.drawer === 'det' && (m.section === 'bans' || m.section === 'evidence' || m.section === 'feed'))) renderDrawer();
    return;
  }
  if (m.type === 'toast') {
    const d = m.data || {};
    toast(d.ok !== false, d.msg);
    if (d.ok !== false) setTimeout(() => refreshTab(true), 350);
    return;
  }
  if (m.type === 'nex') nexFrame(m.data);
});

// Tell the game the page loaded. If this never arrives, the client says so
// instead of leaving a cursor on an empty screen.
post('ready', {});

/* (DevTools watch removed for the website by scripts/sync_panel.py) */

