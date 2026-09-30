import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DIAGNOSTIC_OUTBOX_KEY, DiagnosticRecorder, parseDiagnosticOutbox,
} from '../src/diagnostics.ts';

function recorder() {
  const values = new Map();
  let identity = 0;
  const diagnostics = new DiagnosticRecorder({
    get: (key) => values.get(key) ?? null,
    set: (key, value) => values.set(key, value),
    installationId: () => 'installation',
    hostOs: () => 'macOS',
    hostVersion: () => '12.1.28496',
    identifier: () => `id-${identity += 1}`,
    now: () => '2026-09-30T00:00:00.000Z',
  });
  return { diagnostics, values };
}

test('anonymous diagnostics persist only the structured allowlist', () => {
  const { diagnostics, values } = recorder();
  const event = diagnostics.record({
    event_type: 'query_success', completion_phase: 'ghost', duration_ms: 120,
    candidate_count: 3, completion_ready: true,
  });

  assert.equal(event.installation_id, 'installation');
  assert.equal(event.session_id, 'id-2');
  assert.equal('query' in event, false);
  assert.deepEqual(diagnostics.pending(), [event]);

  diagnostics.remove([event.event_id]);
  assert.deepEqual(diagnostics.pending(), []);
  assert.equal(values.get(DIAGNOSTIC_OUTBOX_KEY), '[]');
});

test('corrupt or privacy-expanding diagnostic queues are surfaced', () => {
  assert.throws(() => parseDiagnosticOutbox('{broken'), /队列损坏/);
  const { diagnostics } = recorder();
  const event = diagnostics.record({ event_type: 'inline_open' });
  assert.throws(
    () => parseDiagnosticOutbox(JSON.stringify([{ ...event, query: '客户文本' }])),
    /格式无效/,
  );
});
