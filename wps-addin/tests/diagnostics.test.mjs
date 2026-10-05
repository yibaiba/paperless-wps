import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DIAGNOSTIC_OUTBOX_KEY, DiagnosticRecorder, parseDiagnosticOutbox,
} from '../src/diagnostics.ts';
import { businessDiagnostic } from '../src/businessDiagnostics.ts';
import { IndexedDbDiagnosticStore } from '../src/diagnosticStore.ts';

function recorder(options = {}) {
  const values = options.values ?? new Map();
  const events = options.events ?? new Map();
  const store = options.store ?? {
    put: async (items) => items.forEach((e) => { if (!events.has(e.event_id)) events.set(e.event_id, e); }),
    list: async (query = {}) => [...events.values()].filter((e) => !query.eventIds || query.eventIds.includes(e.event_id)),
    remove: async (ids) => ids.forEach((id) => events.delete(id)),
  };
  let identity = 0;
  const diagnostics = new DiagnosticRecorder({
    get: (key) => values.get(key) ?? null,
    set: (key, value) => values.set(key, value),
    remove: (key) => values.delete(key), store,
    installationId: () => 'installation',
    hostOs: () => 'macOS',
    hostVersion: () => '12.1.28496',
    identifier: options.identifier ?? (() => `id-${identity += 1}`),
    now: () => '2026-09-30T00:00:00.000Z',
  });
  return { diagnostics, values, events, store };
}

test('anonymous diagnostics persist only the structured allowlist', async () => {
  const { diagnostics, values } = recorder();
  const event = await diagnostics.record({
    event_type: 'query_success', completion_phase: 'ghost', duration_ms: 120,
    candidate_count: 3, completion_ready: true,
  });

  assert.equal(event.installation_id, 'installation');
  assert.equal(event.session_id, 'id-2');
  assert.equal('query' in event, false);
  assert.deepEqual(await diagnostics.pending(), [event]);

  await diagnostics.remove([event.event_id]);
  assert.deepEqual(await diagnostics.pending(), []);
  assert.equal(values.has(DIAGNOSTIC_OUTBOX_KEY), false);
});

test('corrupt or privacy-expanding diagnostic queues are surfaced', async () => {
  assert.throws(() => parseDiagnosticOutbox('{broken'), /队列损坏/);
  const { diagnostics } = recorder();
  const event = await diagnostics.record({ event_type: 'inline_open' });
  assert.throws(
    () => parseDiagnosticOutbox(JSON.stringify([{ ...event, query: '客户文本' }])),
    /格式无效/,
  );
  await assert.rejects(() => diagnostics.record({ event_type: 'query_start', query: '客户文本' }), /格式无效/);
});

test('legacy queues are cleared only after durable migration and readback', async () => {
  const old = await recorder().diagnostics.record({ event_type: 'inline_open' });
  const raw = JSON.stringify([old]); const values = new Map([[DIAGNOSTIC_OUTBOX_KEY, raw]]);
  const good = recorder({ values });
  assert.deepEqual(await good.diagnostics.pending(), [old]);
  assert.equal(values.has(DIAGNOSTIC_OUTBOX_KEY), false);
  const badValues = new Map([[DIAGNOSTIC_OUTBOX_KEY, raw]]);
  const bad = recorder({ values: badValues, store: { put: async () => { throw new Error('磁盘写入失败'); } } });
  await assert.rejects(() => bad.diagnostics.pending(), /磁盘写入失败/);
  assert.equal(badValues.get(DIAGNOSTIC_OUTBOX_KEY), raw);
});

test('parallel windows and upload removal cannot overwrite unrelated events', async () => {
  const events = new Map(); let id = 0; const values = new Map();
  const options = { events, values, identifier: () => `parallel-${++id}` };
  const first = recorder(options).diagnostics, second = recorder(options).diagnostics;
  const written = await Promise.all([first.record({ event_type: 'query_start' }), second.record({ event_type: 'query_success' })]);
  assert.equal((await first.pending()).length, 2);
  await first.remove([written[0].event_id]);
  assert.deepEqual(await second.pending(), [written[1]]);
});

test('legacy changes during migration stay intact and are retried on the next upload', async () => {
  const older = await recorder().diagnostics.record({ event_type: 'inline_open' });
  const newer = { ...older, event_id: 'next' };
  const values = new Map([[DIAGNOSTIC_OUTBOX_KEY, JSON.stringify([older])]]);
  const fixture = recorder({ values }); const original = fixture.store.list;
  let changed = false;
  fixture.store.list = async (options) => {
    if (!changed) { changed = true; values.set(DIAGNOSTIC_OUTBOX_KEY, JSON.stringify([older, newer])); }
    return original(options);
  };
  assert.equal((await fixture.diagnostics.pending()).length, 2);
  assert.equal(values.has(DIAGNOSTIC_OUTBOX_KEY), false);
});

test('asynchronous storage failure is visible and outside the product transaction', async () => {
  const gate = Promise.withResolvers(); const messages = [];
  const fixture = recorder({ store: { put: () => gate.promise } });
  let writes = 0;
  businessDiagnostic({ recordDiagnostic: (e) => fixture.diagnostics.record(e),
    reportBackgroundError: (e) => messages.push(e) }, { event_type: 'completion_accepted' });
  writes++;
  assert.equal(writes, 1); assert.equal(messages.length, 0);
  gate.reject(new Error('IndexedDB 配额不足'));
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(messages[0], /IndexedDB 配额不足/);
  const absent = new IndexedDbDiagnosticStore({ factory: () => undefined });
  await assert.rejects(() => absent.put([]), /不可用/);
});
