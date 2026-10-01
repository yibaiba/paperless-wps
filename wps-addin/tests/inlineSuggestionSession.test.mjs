import assert from 'node:assert/strict';
import { test } from 'node:test';

import { inlineWorkbookContextForQuery } from '../src/inlineSuggestionSession.ts';

test('typed model replaces the stale current product in suggestion context', () => {
  const context = {
    profile: { field_columns: { model: 2, name: 3 } },
    cell: { sheet: '报价表', row: 8, column: 2 },
  };
  const workbook = {
    metadata: { line_bindings: [{
      line_id: 'line-1', sheet: '报价表', row: 8,
      anchor_fingerprint: 'old-1\0旧产品', variant_id: 'old', source_id: 'source-old',
    }] },
    row: {
      sheet: '报价表', row: 8, values: { model: 'OLD-1', name: '旧产品' },
      formula_fields: [], merged_fields: [],
    },
    product: { section: '无纸化系统', selected_variant_id: 'old' },
  };

  const updated = inlineWorkbookContextForQuery(context, workbook, 'NEW-1');

  assert.equal(updated.row.values.model, 'NEW-1');
  assert.equal(updated.product.selected_variant_id, undefined);
  assert.deepEqual(updated.product.sheet_variant_ids, []);
  assert.equal(workbook.row.values.model, 'OLD-1');
});
