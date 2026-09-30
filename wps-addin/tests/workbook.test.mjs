import assert from 'node:assert/strict';
import { test } from 'node:test';

import { assertWritableTargets, scanWorkbook } from '../src/workbook.ts';

const metadata = {
  schema_version: 1,
  workbook_instance_id: 'book',
  line_bindings: [{
    line_id: 'line', sheet: '报价表', row: 3,
    anchor_fingerprint: ['server-x', '服务器'].join('\0'),
    device_id: 'device', variant_id: 'variant', source_id: 'source',
  }],
};

function row(overrides = {}) {
  return {
    sheet: '报价表', row: 3,
    values: { model: 'SERVER-X', name: '服务器', quantity: '2', price: '100', unit: '台' },
    formula_fields: [], merged_fields: [], ...overrides,
  };
}

test('scan creates a canonical line only from a confirmed product binding', () => {
  const result = scanWorkbook([row()], metadata);
  assert.equal(result.unresolved.length, 0);
  assert.deepEqual(result.lines[0], {
    line_id: 'line', sheet: '报价表', row: 3, model: 'SERVER-X', name: '服务器',
    description: '', quantity: '2', unit: '台', brand: '', price: '100', note: '',
    section: '', kind: 'hardware', variant_id: 'variant', source_id: 'source', device_id: 'device',
  });
});

test('formula quantity remains visible as an explicit sync error', () => {
  const result = scanWorkbook([row({ formula_fields: ['quantity'] })], metadata);
  assert.equal(result.lines.length, 0);
  assert.match(result.unresolved[0], /公式/);
});

test('unconfirmed rows are reported instead of guessed', () => {
  const result = scanWorkbook([row()], { ...metadata, line_bindings: [] });
  assert.equal(result.lines.length, 0);
  assert.match(result.unresolved[0], /尚未确认/);
});

test('candidate writes reject formulas and merged cells before mutation', () => {
  assert.throws(() => assertWritableTargets([
    { address: 'B3', formula: '=A3', merged: false },
  ]), /B3.*公式/);
  assert.throws(() => assertWritableTargets([
    { address: 'C3', formula: '', merged: true },
  ]), /C3.*合并区域/);
});
