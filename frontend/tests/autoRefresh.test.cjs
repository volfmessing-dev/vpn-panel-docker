const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const build = fs.mkdtempSync(path.join(os.tmpdir(), 'panel-refresh-test-'));
execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'), path.resolve(__dirname, '../src/lib/autoRefresh.ts'), '--module', 'commonjs', '--target', 'es2022', '--outDir', build]);
const { startAutoRefresh, refreshResources } = require(path.join(build, 'autoRefresh.js'));
after(() => fs.rmSync(build, { recursive: true, force: true }));
async function flush() { for (let i = 0; i < 5; i++) await Promise.resolve(); }
function clock() {
  let time = 0, visible = true, listener, serial = 0;
  const timers = new Map();
  const env = { now: () => time, visible: () => visible, schedule: (run, delay) => { const id = ++serial; timers.set(id, { run, at: time + delay }); return id; }, cancel: id => timers.delete(id), onVisibility: fn => { listener = fn; return () => { listener = undefined; }; } };
  return { env, timers, visibility(value) { visible = value; listener?.(); }, async advance(ms) { const target = time + ms; while (true) { const next = [...timers.entries()].filter(([, t]) => t.at <= target).sort((a,b) => a[1].at - b[1].at)[0]; if (!next) break; time = next[1].at; timers.delete(next[0]); next[1].run(); await flush(); } time = target; await flush(); } };
}
test('starts at 60 seconds, not immediately, and repeats at the chosen interval', async () => {
  const c = clock(); let calls = 0; const stop = startAutoRefresh(async () => { calls++; }, c.env);
  await c.advance(59999); assert.equal(calls, 0); await c.advance(1); assert.equal(calls, 1); await c.advance(60000); assert.equal(calls, 2); stop();
});
test('hidden tab has no polling and becomes eligible only when visible', async () => {
  const c = clock(); let calls = 0; const stop = startAutoRefresh(async () => { calls++; }, c.env);
  c.visibility(false); await c.advance(180000); assert.equal(calls, 0); assert.equal(c.timers.size, 0);
  c.visibility(true); await c.advance(0); assert.equal(calls, 1); stop();
});
test('a slow request cannot stack polls and next poll waits 60 seconds after completion', async () => {
  const c = clock(); let calls = 0, complete; const stop = startAutoRefresh(() => { calls++; return new Promise(resolve => { complete = resolve; }); }, c.env);
  await c.advance(180000); assert.equal(calls, 1); assert.equal(c.timers.size, 0);
  complete(); await flush(); await c.advance(59999); assert.equal(calls, 1); await c.advance(1); assert.equal(calls, 2); stop(); complete(); await flush();
});
test('pause/unmount cancels timer and does not reschedule an already running request', async () => {
  const c = clock(); let complete; const stop = startAutoRefresh(() => new Promise(resolve => { complete = resolve; }), c.env);
  await c.advance(60000); stop(); complete(); await flush(); assert.equal(c.timers.size, 0); c.visibility(true); assert.equal(c.timers.size, 0);
});
test('failed request retries once per interval without a tight loop', async () => {
  const c = clock(); let calls = 0; const stop = startAutoRefresh(async () => { calls++; throw new Error('fixture failure'); }, c.env);
  await c.advance(60000); assert.equal(calls, 1); await c.advance(59999); assert.equal(calls, 1); await c.advance(1); assert.equal(calls, 2); stop();
});
test('switching owners stops the previous page poll', async () => {
  const c = clock(); let old = 0, next = 0; const stopOld = startAutoRefresh(async () => { old++; }, c.env);
  stopOld(); const stopNext = startAutoRefresh(async () => { next++; }, c.env); await c.advance(60000); assert.equal(old, 0); assert.equal(next, 1); stopNext();
});
test('per-view plans exclude unused heavy data and every probe/apply endpoint', () => {
  assert.deepEqual(refreshResources.users, ['users', 'cloud']);
  assert.deepEqual(refreshResources.nodes, ['nodes', 'tunnels', 'cloud']);
  assert.deepEqual(refreshResources['bypass-list'], []);
  for (const [page, resources] of Object.entries(refreshResources)) { if (page !== 'dashboard') assert.ok(!resources.includes('bypass')); assert.ok(!resources.some(name => /health|facts|apply/.test(name))); }
});
