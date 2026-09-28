const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'templates', 'server.html'), 'utf8');
const start = html.indexOf('function viewScreenshots() {');
const end = html.indexOf('/* Configuration.', start);
assert.ok(start >= 0 && end > start);

const context = {
  data: {
    evidence: [
      { id: 'new', at: 300, detection: 'New', player: { name: 'New Player' },
        screenshot: { status: 'requested' }, images: 0 },
      { id: 'middle', at: 200, detection: 'Middle', player: { name: 'Middle Player' },
        screenshot: { status: 'captured' }, images: 1 },
      { id: 'old', at: 100, detection: 'Old', player: { name: 'Old Player' },
        screenshot: { status: 'skipped' }, images: 0 },
    ],
    role: 'administrator', online: false, snapshot: { players: [], integrations: { screenshots: 'started' } },
  },
  SERVER: 'test',
  icon: () => '',
  escapeHtml: (value) => String(value),
  num: (value) => String(value),
  offlineNote: () => '',
};
vm.createContext(context);
vm.runInContext(html.slice(start, end), context);
const gallery = vm.runInContext('viewScreenshots()', context);
const positions = ['new', 'middle', 'old'].map((id) => gallery.indexOf('sc-cap-id">' + id));
assert.ok(positions.every((position) => position >= 0));
assert.ok(positions[0] < positions[1] && positions[1] < positions[2],
  'pending and captured cards must share the newest-first case order');
console.log('evidence gallery: pending and captured cases stay in order');
