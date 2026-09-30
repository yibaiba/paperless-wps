import assert from 'node:assert/strict';
import { test } from 'node:test';

import { suggestionContext } from '../src/suggestionContext.ts';

test('suggestion context follows the nearest confirmed products above the active row', () => {
  const context = suggestionContext({
    cell: { sheet: '报价表', row: 12 },
    row: { values: { section: '无纸化系统' } },
    metadata: { line_bindings: [
      { sheet: '报价表', row: 7, variant_id: 'older', source_id: 'older-source' },
      { sheet: '其他表', row: 11, variant_id: 'other-sheet', source_id: 'other-source' },
      { sheet: '报价表', row: 10, variant_id: 'nearest', source_id: 'nearest-source' },
      { sheet: '报价表', row: 14, variant_id: 'below', source_id: 'below-source' },
    ] },
  });
  assert.equal(context.selected_variant_id, undefined);
  assert.deepEqual(context.previous_variant_ids, ['nearest', 'older']);
  assert.deepEqual(context.previous_source_ids, ['nearest-source', 'older-source']);
  assert.deepEqual(context.next_variant_ids, ['below']);
  assert.deepEqual(context.next_source_ids, ['below-source']);
  assert.equal(context.system, '无纸化系统');
});

test('suggestion context identifies the current product and inherits a blank section', () => {
  const context = suggestionContext({
    cell: { sheet: '报价表', row: 12 },
    row: { values: {} },
    inheritedSection: '视频会议系统',
    metadata: { line_bindings: [
      { sheet: '报价表', row: 12, variant_id: 'current', source_id: 'current-source' },
      { sheet: '报价表', row: 13, variant_id: 'next', source_id: 'next-source' },
    ] },
  });
  assert.equal(context.selected_variant_id, 'current');
  assert.equal(context.selected_source_id, 'current-source');
  assert.equal(context.section, '视频会议系统');
  assert.deepEqual(context.next_variant_ids, ['next']);
});

test('suggestion context does not mutate workbook binding order', () => {
  const bindings = [
    { sheet: '报价表', row: 2, variant_id: 'first' },
    { sheet: '报价表', row: 8, variant_id: 'second' },
  ];
  suggestionContext({
    cell: { sheet: '报价表', row: 10 },
    row: { values: {} },
    metadata: { line_bindings: bindings },
  });
  assert.deepEqual(bindings.map((item) => item.variant_id), ['first', 'second']);
});
