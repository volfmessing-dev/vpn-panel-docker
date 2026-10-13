const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const frontend = path.resolve(__dirname, '..');
const build = fs.mkdtempSync(path.join(os.tmpdir(), 'node-status-test-'));
execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'), path.join(frontend, 'src/lib/nodeTunnelStatus.ts'), '--module', 'commonjs', '--target', 'es2022', '--outDir', build]);
const { nodeTunnelStatuses: statuses } = require(path.join(build, 'lib/nodeTunnelStatus.js'));
after(() => fs.rmSync(build, { recursive: true, force: true }));
const now = 1800000000000;
const home = { id: 1, name: 'MikroTik', role: 'mikrotik', host: '10.202.0.2' };
const ru = { id: 2, name: 'RU_Cloud', role: 'ru_cloud', host: '192.0.2.2' };
const nl = { id: 3, name: 'Exit_A', role: 'amnezia_exit', host: '192.0.2.3' };
const ger = { id: 4, name: 'Archived_B', role: 'amnezia_exit', host: '192.0.2.4' };
const nodes = [home, ru, nl, ger];
const tunnels = [{ source_node_id: 1, target_node_id: 2 }, { source_node_id: 2, target_node_id: 3 }, { source_node_id: 2, target_node_id: 4 }];
function snapshot(homeAge = 20, flags = ['LOWER_UP']) {
  return { node_id: 2, status: 'up', interfaces: [
    { name: 'wg-ru-cloud', flags, peers: [
      { public_key: 'home', endpoint: '192.0.2.50:8443', allowed_ips: ['10.202.0.2/32'], latest_handshake: homeAge === null ? 0 : now / 1000 - homeAge },
      { public_key: 'phone', endpoint: '192.0.2.51:5000', allowed_ips: ['10.90.0.11/32'], latest_handshake: now / 1000 - 1 },
    ] },
    { name: 'awg1', flags: ['LOWER_UP'], peers: [{ public_key: 'nl', endpoint: '192.0.2.3:51820', allowed_ips: ['0.0.0.0/0'], latest_handshake: now / 1000 - 10 }] },
  ] };
}
function check(node, snap = snapshot(), stale = false) { return statuses(node, nodes, tunnels, snap, now, true, stale); }
test('matches home by its tunnel IP and labels recent activity', () => {
  const result = check(home)[0]; assert.equal(result.label, 'Туннель активен'); assert.equal(result.tone, 'up'); assert.match(result.detail, /20 сек/);
});
test('fresh phone handshake cannot hide an old or missing home handshake', () => {
  for (const age of [180, 3600, null]) { const result = check(home, snapshot(age))[0]; assert.equal(result.tone, 'warning'); assert.equal(result.label, 'Нет свежего handshake'); }
});
test('interface must be raised even with a recent handshake', () => {
  const result = check(home, snapshot(20, []))[0]; assert.equal(result.label, 'Интерфейс не поднят'); assert.equal(result.tone, 'warning');
});
test('NL matches its endpoint instead of the catch-all AllowedIPs', () => {
  assert.equal(check(nl)[0].label, 'Туннель активен');
  assert.equal(check({ ...nl, host: '192.0.2.99' })[0].tone, 'neutral');
});
test('gateway displays each current remote connection separately, excluding archive', () => {
  const result = check(ru); assert.equal(result.length, 2); assert.deepEqual(result.map(r => r.title), ['Туннель к MikroTik', 'Туннель к Exit_A']);
});
test('stale, unavailable and missing snapshots never show a green status', () => {
  for (const snap of [null, { ...snapshot(), status: 'down' }]) assert.equal(check(home, snap)[0].tone, 'neutral');
  assert.equal(check(home, snapshot(), true)[0].tone, 'neutral');
  assert.equal(statuses(home, nodes, tunnels, snapshot(), now, false, false)[0].tone, 'neutral');
});
test('a configured public key identifies a peer when registry hostname differs', () => {
  const configured = [{ source_node_id: 1, target_node_id: 2, source_public_key: 'home' }];
  assert.equal(statuses({ ...home, host: 'router.example.test' }, nodes, configured, snapshot(), now, true, false)[0].tone, 'up');
});
