const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'templates', 'server.html'), 'utf8');
const state = html.slice(html.indexOf('const pendingChanges ='), html.indexOf('const num ='));
assert.ok(state.startsWith('const pendingChanges ='));

const checks = `
const snap = (revision, enabled, direct) => ({
  config: { persistence: { revision, verified: true, dirty: false },
    settings: { 'test.enabled': { value: enabled } } },
  integrations: { webhooks: [{ category: 'bans', configuredDirect: direct }] },
  protections: [], detectors: [],
});
const fresh = (snapshot, commands) => ({ snapshot, commands, online: true });
const setting = { type: 'setting', path: 'test.enabled', value: false };
pendingChanges.set('setting:test.enabled', { id: 'one', body: setting, label: 'Test', at: Date.now(), revision: 1 });
showServerData(fresh(snap(1, true, true), [{ id: 'one', status: 'pending' }]));
assert.equal(data.snapshot.config.settings['test.enabled'].value, false,
  'the desired value must survive a stale heartbeat');
showServerData(fresh(snap(1, true, true), [{ id: 'one', status: 'succeeded' }]));
assert.equal(pendingChanges.has('setting:test.enabled'), true,
  'an acknowledgement without a newer saved snapshot must not clear the pending value');
showServerData(fresh(snap(2, false, true), [{ id: 'one', status: 'succeeded' }]));
assert.equal(pendingChanges.has('setting:test.enabled'), false);
const hook = { type: 'webhook', category: 'bans', url: '' };
pendingChanges.set('webhook:bans', { id: 'two', body: hook, label: 'Bans', at: Date.now(), revision: 2 });
showServerData(fresh(snap(2, false, true), [{ id: 'two', status: 'pending' }]));
assert.equal(data.snapshot.integrations.webhooks[0].configuredDirect, false);
showServerData(fresh(snap(3, false, false), [{ id: 'two', status: 'succeeded' }]));
assert.equal(pendingChanges.has('webhook:bans'), false);
pendingChanges.set('setting:test.enabled', { id: 'three', body: setting, label: 'Test', at: Date.now(), revision: 3 });
showServerData(fresh(snap(3, true, false), [{ id: 'three', status: 'failed', result: 'disk full' }]));
assert.equal(pendingChanges.has('setting:test.enabled'), false);
assert.equal(configEdits['test.enabled'], false, 'failed edits must remain staged for retry');
assert.equal(messages.at(-1).tone, 'bad');
`;

const context = {
  assert, Date, JSON, Map, Object, Number, String,
  msg: {}, messages: [], configEdits: {},
  note(_target, message, tone) { this.messages.push({ message, tone }); },
  protectionFields(p) { return p; },
};
// Avoid binding `this` to the sandbox when the UI calls note as a plain function.
context.note = (_target, message, tone) => context.messages.push({ message, tone });
vm.runInNewContext('let data = null, serverData = null;\n' + state + '\n' + checks, context);
console.log('dashboard state: optimistic value, acknowledgement, webhook clear and refusal passed');
