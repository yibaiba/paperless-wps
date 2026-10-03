import test from 'node:test';
import assert from 'node:assert/strict';
import '../../wps-native-probe/probe.js';

test('probe logs actual callbacks, never equates OnKey with native editing support', () => {
  const keys = [], listeners = new Map();
  const app = { Version: 'test', Build: 'unit', OperatingSystem: 'unit',
    ActiveCell: { Value2: 'abc' }, OnKey: (...args) => keys.push(args),
    ApiEvent: { AddApiEventListener: (name, cb) => listeners.set(name, cb),
      RemoveApiEventListener: (name) => listeners.delete(name) } };
  const probe = new globalThis.NativeProbe(app, () => 'unit-time');
  probe.start(); probe.sample(); probe.arm(); probe.tab(); probe.stop();
  assert.deepEqual(keys, [['{TAB}', 'NativeProbeTab'], ['{TAB}']]);
  assert.equal(listeners.size, 0);
  const report = probe.report();
  assert.ok(Object.values(report.capabilities).every((v) => v.status === 'not_verified'));
  assert.equal(report.events.find((e) => e.type === 'committed_cell_read').value_length, 3);
  assert.equal(JSON.stringify(report).includes('abc'), false);
  assert.equal(report.native_integration_enabled, false);
});

test('probe restores registered Tab on deactivation and exposes cleanup failure', () => {
  const keys = [], listeners = new Map(); let failCleanup = false;
  const app = { OnKey: (...args) => keys.push(args), ApiEvent: {
    AddApiEventListener: (name, fn) => listeners.set(name, fn),
    RemoveApiEventListener: (name) => {
      if (failCleanup) throw new Error('host refused cleanup');
      listeners.delete(name);
    },
  } };
  const probe = new globalThis.NativeProbe(app, () => 'unit-time');
  probe.start(); probe.arm(); listeners.get('WindowDeactivate')();
  assert.deepEqual(keys.at(-1), ['{TAB}']);
  failCleanup = true; assert.throws(() => probe.stop(), /事件清理失败/);
  assert.equal(probe.report().events.at(-1).remaining_subscriptions, 6);
  failCleanup = false; probe.stop(); assert.equal(listeners.size, 0);
});
