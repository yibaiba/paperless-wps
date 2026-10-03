import assert from 'node:assert/strict';
import { test } from 'node:test';

import { applyCandidate } from '../src/candidateAcceptance.ts';

test('accepting an inline candidate writes product identity into workbook metadata', () => {
  let saved;
  const host = {
    writeCandidate: () => undefined,
    readRow: (_profile, row) => ({
      sheet: '报价表', row: 4, values: { model: 'M-1', name: '产品' },
      formula_fields: [], merged_fields: [],
    }),
    readRows: () => { throw new Error('单行接受不得读取整表'); },
    writeMetadata: (value) => { saved = value; },
  };
  const metadata = { schema_version: 1, workbook_instance_id: 'w1', line_bindings: [] };
  const candidate = { variant_id: 'v1', source_id: 's1' };
  applyCandidate({
    host,
    profile: { id: 'p1', revision: 2 },
    cell: { row: 4 },
    metadata,
    candidate,
    section: '无纸化会议系统',
  });
  assert.equal(saved.profile_id, 'p1');
  assert.equal(saved.profile_revision, 2);
  assert.equal(saved.line_bindings[0].variant_id, 'v1');
  assert.equal(saved.line_bindings[0].source_id, 's1');
  assert.equal(saved.line_bindings[0].section, '无纸化会议系统');
});

test('replacing a product preserves the confirmed business line identity', () => {
  let saved;
  const oldBinding = {
    line_id: 'line-old', device_id: 'device-old', sheet: '报价表', row: 4,
    anchor_fingerprint: 'old-1\0旧产品', variant_id: 'old', source_id: 'old-source',
  };
  const host = {
    writeCandidate: () => undefined,
    readRow: () => ({
      sheet: '报价表', row: 4, values: { model: 'NEW-1', name: '新产品' },
      formula_fields: [], merged_fields: [],
    }),
    writeMetadata: (value) => { saved = value; },
  };

  applyCandidate({
    host,
    profile: { id: 'p1', revision: 1 },
    cell: { row: 4 },
    metadata: { line_bindings: [oldBinding] },
    candidate: { variant_id: 'new', source_id: 'new-source' },
    lineBinding: oldBinding,
  });

  assert.equal(saved.line_bindings.length, 1);
  assert.equal(saved.line_bindings[0].line_id, 'line-old');
  assert.equal(saved.line_bindings[0].device_id, 'device-old');
  assert.equal(saved.line_bindings[0].variant_id, 'new');
});

test('accepting on a moved row does not overwrite the displaced binding', () => {
  let saved;
  const displaced = {
    line_id: 'line-deleted', sheet: '报价表', row: 4,
    anchor_fingerprint: 'deleted\0已删除', variant_id: 'deleted', source_id: 'source-deleted',
  };
  const moved = {
    line_id: 'line-moved', device_id: 'device-moved', sheet: '报价表', row: 5,
    anchor_fingerprint: 'moved\0已移动', variant_id: 'moved', source_id: 'source-moved',
  };
  const host = {
    writeCandidate: () => undefined,
    readRow: () => ({
      sheet: '报价表', row: 4, values: { model: 'NEW-1', name: '新产品' },
      formula_fields: [], merged_fields: [],
    }),
    writeMetadata: (value) => { saved = value; },
  };

  applyCandidate({
    host,
    profile: { id: 'p1', revision: 1 },
    cell: { row: 4 },
    metadata: { line_bindings: [displaced, moved] },
    candidate: { variant_id: 'new', source_id: 'new-source' },
    lineBinding: moved,
  });

  assert.equal(saved.line_bindings.length, 2);
  assert.ok(saved.line_bindings.some((item) => item.line_id === 'line-deleted'));
  const updated = saved.line_bindings.find((item) => item.line_id === 'line-moved');
  assert.equal(updated.row, 4);
  assert.equal(updated.device_id, 'device-moved');
});
