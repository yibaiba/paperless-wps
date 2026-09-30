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
  assert.deepEqual(context.sheet_variant_ids, ['nearest', 'below', 'older']);
  assert.deepEqual(context.sheet_source_ids, [
    'nearest-source', 'below-source', 'older-source',
  ]);
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

test('sheet context remembers products beyond the local sequence window', () => {
  const line_bindings = Array.from({ length: 12 }, (_, index) => ({
    sheet: '报价表', row: index + 2,
    variant_id: `variant-${index}`, source_id: `source-${index}`,
  }));

  const context = suggestionContext({
    cell: { sheet: '报价表', row: 20 },
    row: { values: {} },
    metadata: { line_bindings },
  });

  assert.equal(context.previous_variant_ids.length, 8);
  assert.equal(context.sheet_variant_ids.length, 12);
  assert.ok(context.sheet_variant_ids.includes('variant-0'));
});

test('completed binding metadata isolates context to the active section', () => {
  const context = suggestionContext({
    cell: { sheet: '报价表', row: 20 },
    row: { values: { section: '表决系统' } },
    metadata: { line_bindings: [
      { sheet: '报价表', row: 4, section: '无纸化系统', variant_id: 'paperless' },
      { sheet: '报价表', row: 16, section: '表决系统', variant_id: 'voting-host' },
      { sheet: '报价表', row: 22, section: '表决系统', variant_id: 'voting-terminal' },
    ] },
  });

  assert.deepEqual(context.previous_variant_ids, ['voting-host']);
  assert.deepEqual(context.next_variant_ids, ['voting-terminal']);
  assert.deepEqual(context.sheet_variant_ids, ['voting-terminal', 'voting-host']);
});

test('legacy bindings without section metadata retain whole-sheet context', () => {
  const context = suggestionContext({
    cell: { sheet: '报价表', row: 20 },
    row: { values: { section: '表决系统' } },
    metadata: { line_bindings: [
      { sheet: '报价表', row: 4, variant_id: 'legacy-paperless' },
      { sheet: '报价表', row: 16, variant_id: 'legacy-voting' },
    ] },
  });

  assert.deepEqual(context.previous_variant_ids, ['legacy-voting', 'legacy-paperless']);
});
