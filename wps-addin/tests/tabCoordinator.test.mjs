import assert from 'node:assert/strict';
import { test } from 'node:test';

import { TAB_SESSION_KEY, WpsTabCoordinator } from '../src/tabCoordinator.ts';

function setup() {
  const storage = new Map();
  const onKey = [];
  const app = {
    OnKey: (...args) => onKey.push(args),
    PluginStorage: {
      getItem: (key) => storage.get(key),
      setItem: (key, value) => storage.set(key, String(value)),
    },
  };
  const coordinator = new WpsTabCoordinator({
    app,
    get: (key) => storage.get(key) ?? null,
    set: (key, value) => storage.set(key, value),
    operationId: () => 'operation-1',
  });
  return { coordinator, onKey, storage };
}

test('host Tab is registered only for the current actionable revision', () => {
  const { coordinator, onKey } = setup();
  coordinator.activate('session-1', 'ghost:0');
  coordinator.activate('session-1', 'ghost:0');

  assert.deepEqual(onKey, [['{TAB}', 'PresalesTab']]);
  assert.equal(coordinator.claim('session-1'), 'operation-1');
  assert.equal(coordinator.claim('session-1'), null);

  coordinator.activate('session-1', 'list:1');
  assert.equal(coordinator.claim('session-1'), 'operation-1');
  assert.equal(onKey.length, 2);
});

test('stale cleanup cannot restore Tab owned by a newer inline session', () => {
  const { coordinator, onKey, storage } = setup();
  coordinator.activate('new-session', 'ghost:0');
  coordinator.restore('old-session');
  assert.ok(storage.get(TAB_SESSION_KEY));
  assert.equal(onKey.length, 1);

  coordinator.restore('new-session');
  assert.equal(storage.get(TAB_SESSION_KEY), '');
  assert.deepEqual(onKey.at(-1), ['{TAB}']);
});

test('missing WPS key or shared-storage APIs are reported explicitly', () => {
  const coordinator = new WpsTabCoordinator({
    app: {}, get: () => null, set: () => {},
  });
  assert.deepEqual(coordinator.capabilityIssues(), ['Application.OnKey', 'PluginStorage']);
});
