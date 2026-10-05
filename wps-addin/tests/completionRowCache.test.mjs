import assert from 'node:assert/strict';
import { test } from 'node:test';
import { contextWorkload } from './context-workload.mjs';
import { completionRowCache } from '../src/businessWorkbook.ts';

test('pure queries reuse parsed rows; one ordinary quantity edit reparses only its row', () => {
  const work = contextWorkload();
  work.request(); const cache = completionRowCache(work.index);
  const initial = cache.parsedRows;
  for (let i = 0; i < 50; i++) work.request(`query-${i}`);
  assert.equal(cache.parsedRows, initial);
  const before = work.metrics.bindingReads;
  work.rows[4].values = { ...work.rows[4].values, quantity: '5' };
  work.index.changed({ sheet: 'q', row: 6, rowCount: 1 });
  const result = work.request();
  assert.equal(cache.parsedRows, initial + 1);
  assert.equal(result.lines.find((r) => r.row === 6).quantity, '5');
  assert.ok(work.metrics.bindingReads - before < 100);
  assert.equal(work.metrics.fullReads, 1);
});

test('binding revisions, structural changes and protected cells invalidate parsed state', () => {
  const work = contextWorkload(4); work.request();
  work.metadata.line_bindings = work.metadata.line_bindings.map((b) => b.row === 3 ? { ...b, variant_id: 'new' } : b);
  assert.equal(work.request().lines.find((r) => r.row === 3).variant_id, 'new');
  work.rows[1] = { ...work.rows[1], formula_fields: ['quantity'] };
  work.index.changed({ sheet: 'q', row: 3, rowCount: 1 });
  assert.equal(work.request().unresolved_rows[0].reason_code, 'formula_business_value');
  work.index.changed({ sheet: 'q', structural: true }); work.request();
  assert.equal(work.metrics.fullReads, 2);
});
