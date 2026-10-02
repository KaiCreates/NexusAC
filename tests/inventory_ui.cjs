const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'app/templates/server.html'), 'utf8');
const start = html.indexOf('const INV_ROLES =');
const end = html.indexOf('const VIEWS =', start);
assert.ok(start >= 0 && end > start);
const code = html.slice(start, end);
const manifest = fs.readFileSync(path.join(root, 'app/static/item-images/manifest.js'), 'utf8');
const context = {
  window: {},
  data: { role: 'administrator', online: true },
  SERVER: 'test',
  api: () => {},
  render: () => {},
  icon: (name) => `<svg data-icon="${name}"></svg>`,
  num: (n) => String(n ?? 0),
  escapeHtml: (value) => String(value ?? '').replace(/[&<>"']/g, (char) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]),
  panel: (title, inner) => `<section class="panel"><h3>${title}</h3>${inner}</section>`,
  offlineNote: () => '',
  setTimeout,
};
vm.createContext(context);
vm.runInContext(manifest + code, context);
vm.runInContext(`
  inv.search = { query: '', rows: [{ identifier: 'char:1', name: 'Avery', online: true, src: 4 }] };
  inv.view = { identifier: 'char:1', name: 'Avery', online: true, live: true,
    items: [{ slot: 1, name: 'water', label: 'Water', count: 3 }], vehicles: [], stashes: [] };
`, context);
const output = vm.runInContext('viewInventories()', context);
assert.match(output, /class="inv-layout"/);
assert.match(output, /class="inv-character selected"/);
assert.match(output, /class="inv-workspace"/);
assert.match(output, /item-images\/water\.webp/);
assert.match(output, /class="inv-item-count">×3/);
assert.ok(fs.existsSync(path.join(root, 'app/static/item-images/water.webp')));

const fallback = vm.runInContext(
  `invItems([{ slot: 2, name: '../missing', label: '<unknown>', count: 1 }], '')`, context,
);
assert.match(fallback, /inv-item-fallback/);
assert.match(fallback, /&lt;unknown&gt;/);
assert.doesNotMatch(fallback, /src=".*missing/);
console.log('inventory UI: separate panes, item artwork, fallback, and escaping passed');
