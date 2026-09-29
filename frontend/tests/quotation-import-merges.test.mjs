import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mappedRows, importOperations } from '../src/features/configuration/quotation/importing/model.ts';
import { withMergedNotes } from '../src/features/configuration/quotation/importing/mergedNotes.ts';

const matrix = [['型号', '数量', '单价', '备注'], ['INPUT', '2', '0', '选配\n现场确认'], ['OUTPUT']];
const mapping = { model: 0, quantity: 1, price: 2, note: 3 };
const region = { range: 'D2:D3', start_row: 2, end_row: 3, start_column: 4, end_column: 4 };
const options = { choices: [{ key: 'choice', variantId: 'v', sourceId: 's', name: '设备', unit: '台' }], evidence: '隔离测试', newId: () => 'd' };
const context = { matrix, mapping, header: 0, merges: [region] };

test('vertical notes carry provenance to all details but raw cells and numeric blanks stay intact', () => {
  const original = mappedRows(matrix, 0, mapping), before = structuredClone(original);
  const rows = withMergedNotes(original, context);
  assert.deepEqual(original, before);
  assert.equal(rows[1].note, '选配\n现场确认');
  assert.equal(rows[1].mergedNoteRange, 'D2:D3');
  assert.deepEqual(rows[1].raw, ['OUTPUT']);
  assert.equal(rows[1].quantity, '');
  assert.equal(rows[1].price, '');
  assert.equal(rows[0].price, '0');
  const row = { ...rows[1], choice: 'choice', kind: 'hardware', quantity: '1' };
  const operations = importOperations([row], options);
  assert.equal(operations.find(o => o.action === 'device_put').value.note, row.note);
  assert.match(operations.find(o => o.action === 'price_set').value.evidence, /D2:D3/);
  assert.equal(operations.find(o => o.action === 'price_set').value.unit_price, null);
});

test('horizontal merges, header merges and numeric columns are not inherited', () => {
  const rows = mappedRows(matrix, 0, mapping);
  for (const merge of [
    { ...region, end_column: 5 },
    { ...region, start_row: 1 },
    { ...region, start_column: 2, end_column: 2 },
  ]) assert.equal(withMergedNotes(rows, { ...context, merges: [merge] })[1].note, '');
  assert.deepEqual(withMergedNotes(rows, { ...context, mapping: { model: 0 } }), rows);
});

test('explicit row notes are preserved and changing mappings rebuilds the projection', () => {
  const rows = mappedRows(matrix, 0, mapping);
  rows[1].note = '明确逐行备注';
  assert.equal(withMergedNotes(rows, context)[1].note, '明确逐行备注');
  const remapped = withMergedNotes(mappedRows(matrix, 0, { model: 0 }), { ...context, mapping: { model: 0 } });
  assert.equal(remapped[1].mergedNoteRange, undefined);
});

test('deleted or orphaned role references fail before a batch can be submitted', () => {
  const row = { ...mappedRows(matrix, 0, mapping)[0], choice: 'choice', kind: 'hardware', systemId: 'system', requirementId: 'deleted' };
  const configuration = { systems: [{ id: 'system' }], requirements: [], devices: [{ id: 'existing' }] };
  for (const existingDeviceId of [undefined, 'existing']) {
    assert.throws(() => importOperations([{ ...row, existingDeviceId }], { ...options, configuration }), /已选角色不存在/);
    assert.throws(() => importOperations([{ ...row, existingDeviceId, systemId: undefined }], { ...options, configuration }), /缺少所属系统/);
  }
});
