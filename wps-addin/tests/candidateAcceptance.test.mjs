import assert from 'node:assert/strict';
import { test } from 'node:test';

import { applyCandidate } from '../src/candidateAcceptance.ts';

test('accepting an inline candidate writes product identity into workbook metadata', () => {
  let saved;
  const host = {
    writeCandidate: () => undefined,
    readRows: () => [{
      sheet: '报价表', row: 4, values: { model: 'M-1', name: '产品' },
      formula_fields: [], merged_fields: [],
    }],
    writeMetadata: (value) => { saved = value; },
  };
  const metadata = { schema_version: 1, workbook_instance_id: 'w1', line_bindings: [] };
  const candidate = { variant_id: 'v1', source_id: 's1' };
  applyCandidate(host, { id: 'p1', revision: 2 }, { row: 4 }, metadata, candidate);
  assert.equal(saved.profile_id, 'p1');
  assert.equal(saved.profile_revision, 2);
  assert.equal(saved.line_bindings[0].variant_id, 'v1');
  assert.equal(saved.line_bindings[0].source_id, 's1');
});
