import assert from 'node:assert/strict';
import { test } from 'node:test';

import { validateMappedHeaders, validateMapping } from '../src/mappingValidation.ts';

test('an empty workbook can validate a complete header mapping', () => {
  const mapping = { name: 2, model: 3, quantity: 5 };
  assert.doesNotThrow(() => validateMapping(mapping, ['name', 'model']));
  assert.doesNotThrow(() => validateMappedHeaders(
    mapping, ['序号', '产品名称', '产品型号', '产品说明', '数量'],
  ));
});

test('mapping rejects a column outside the selected header row', () => {
  assert.throws(
    () => validateMappedHeaders({ model: 3, quantity: 5 }, ['序号', '产品名称']),
    /第 3 列没有表头/,
  );
});
