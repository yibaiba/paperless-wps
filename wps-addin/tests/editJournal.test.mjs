import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyNextEdit, restoreJournal } from '../src/editJournal.ts';
import { MetadataRecords, readMetadataRecords, writeMetadataRecords } from '../src/metadataRecords.ts';
import { rowBusinessOperations } from '../src/businessRowOperations.ts';

function fixture() {
  let metadata = { schema_version: 2, workbook_instance_id: 'book', line_bindings: [],
    business: { local_revision: 0, scopes: [], operations: [], recent_edits: [] } };
  const cells = new Map([[1, 'old'], [2, 'old name']]);
  const journals = new Map();
  const host = {
    readCell: (cell) => ({ ...cell, value: cells.get(cell.column), formula: '', merged: false }),
    writeCellValue: (cell, value) => cells.set(cell.column, value),
    readMetadata: () => structuredClone(metadata),
    writeMetadata: (value) => { metadata = structuredClone(value); },
    journals: () => [...journals.values()],
    writeJournal: (value) => journals.set(value.operation_id, structuredClone(value)),
  };
  const suggestion = { id: 'next', local_revision: 0, applicable: true,
    patches: [
      { sheet: '报价', row: 4, column: 1, field: 'model', before: 'old', after: 'new' },
      { sheet: '报价', row: 4, column: 2, field: 'name', before: 'old name', after: 'new name' },
    ], line_bindings: [{ line_id: 'line', sheet: '报价', row: 4, variant_id: 'v', source_id: 's' }],
    business_operations: [],
  };
  return { host, suggestion, cells, journals };
}

test('group apply is idempotent and undo restores cells plus identity', () => {
  const f = fixture();
  applyNextEdit({ ...f, operationId: 'op' });
  applyNextEdit({ ...f, operationId: 'op' });
  assert.equal(f.host.readMetadata().business.local_revision, 1);
  restoreJournal(f.host, f.journals.get('op'));
  assert.equal(f.cells.get(1), 'old');
  assert.deepEqual(f.host.readMetadata().line_bindings, []);
  assert.equal(f.host.readMetadata().business.recent_edits.at(-1).kind, 'undo');
});

test('partial writes roll back and never report success', () => {
  const f = fixture();
  f.host.writeCellValue = (cell, value) => {
    if (cell.column === 2 && value === 'new name') throw new Error('宿主写入失败');
    f.cells.set(cell.column, value);
  };
  assert.throws(() => applyNextEdit({ ...f, operationId: 'op' }), /已恢复/);
  assert.equal(f.cells.get(1), 'old');
  assert.equal(f.journals.get('op').state, 'restored');
});

test('failed recovery retains the journal and reports actual failure', () => {
  const f = fixture();
  f.host.writeCellValue = (cell, value) => {
    if (cell.column === 2 || value === 'old') throw new Error('拒绝写入');
    f.cells.set(cell.column, value);
  };
  assert.throws(() => applyNextEdit({ ...f, operationId: 'op' }), /恢复未完成/);
  assert.equal(f.journals.get('op').state, 'recovery_required');
  assert.equal(f.cells.get(1), 'new');
});

test('undo does not overwrite a subsequent manual edit', () => {
  const f = fixture();
  applyNextEdit({ ...f, operationId: 'op' });
  f.cells.set(1, 'manual');
  assert.throws(() => restoreJournal(f.host, f.journals.get('op')), /已被修改/);
  assert.equal(f.cells.get(1), 'manual');
});

test('formula and stale-context checks occur before journaling or writing', () => {
  const f = fixture();
  f.suggestion.local_revision = 3;
  assert.throws(() => applyNextEdit({ ...f, operationId: 'op' }), /上下文/);
  f.suggestion.local_revision = 0;
  const read = f.host.readCell;
  f.host.readCell = (cell) => ({ ...read(cell), formula: '=SUM(A1:A3)' });
  assert.throws(() => applyNextEdit({ ...f, operationId: 'op' }), /公式/);
  assert.equal(f.journals.size, 0);
});

test('record store chunks large values and pointer failure preserves the old state', () => {
  const cells = new Map([[1, '{}']]);
  let failRoot = false;
  const store = new MetadataRecords({ read: (row) => cells.get(row) ?? '', write: (row, value) => {
    if (row === 1 && failRoot) throw new Error('root failure');
    assert.ok(value.length <= 32767);
    cells.set(row, value);
  } });
  const metadata = { schema_version: 2, workbook_instance_id: 'book', line_bindings: [],
    business: { operations: [{ action: 'large', text: 'a'.repeat(70000) }] } };
  writeMetadataRecords(store, metadata);
  assert.deepEqual(readMetadataRecords(store), metadata);
  store.write({ 'journal/op': { state: 'prepared' } });
  failRoot = true;
  assert.throws(() => writeMetadataRecords(store, { ...metadata, workbook_instance_id: 'changed' }));
  assert.equal(readMetadataRecords(store).workbook_instance_id, 'book');
  assert.equal(store.records('journal/')['journal/op'].state, 'prepared');
});

test('undo preserves unrelated later identities and business settings', () => {
  const f = fixture();
  f.suggestion.business_operations = [{ action: 'requirement_put', value: { id: 'own' } }];
  applyNextEdit({ ...f, operationId: 'op' });
  const metadata = f.host.readMetadata();
  metadata.line_bindings.push({ line_id: 'other', sheet: 'other', row: 8 });
  metadata.business.operations.push({ action: 'requirement_put', value: { id: 'other' } });
  metadata.business.scopes.push({ system_id: 'later-system' });
  f.host.writeMetadata(metadata);
  restoreJournal(f.host, f.journals.get('op'));
  assert.deepEqual(f.host.readMetadata().line_bindings, [{ line_id: 'other', sheet: 'other', row: 8 }]);
  assert.deepEqual(f.host.readMetadata().business.operations, [{ action: 'requirement_put', value: { id: 'other' } }]);
  assert.equal(f.host.readMetadata().business.scopes[0].system_id, 'later-system');
});

test('undo after sync appends inverse operations without rolling back project baseline', () => {
  const f = fixture();
  f.suggestion.inverse_business_operations = [{ action: 'remove', collection: 'requirements', id: 'own' }];
  applyNextEdit({ ...f, operationId: 'op' });
  f.host.writeMetadata({ ...f.host.readMetadata(), binding: { binding_revision: 4, base_revision: 12 } });
  restoreJournal(f.host, f.journals.get('op'));
  assert.equal(f.host.readMetadata().binding.base_revision, 12);
  assert.deepEqual(f.host.readMetadata().business.operations, f.suggestion.inverse_business_operations);
});

test('uncompleted journal prevents a second group from writing', () => {
  const f = fixture();
  f.host.writeJournal({ operation_id: 'unfinished', state: 'prepared' });
  assert.throws(() => applyNextEdit({ ...f, operationId: 'next' }), /未完成/);
  assert.equal(f.cells.get(1), 'old');
});

test('interrupted undo resumes the original undo intent without losing its journal', () => {
  const f = fixture();
  applyNextEdit({ ...f, operationId: 'op' });
  const write = f.host.writeCellValue;
  f.host.writeCellValue = (cell, value) => {
    if (cell.column === 1) throw new Error('宿主中断');
    write(cell, value);
  };
  assert.throws(() => restoreJournal(f.host, f.journals.get('op')), /报价 4:1/);
  assert.equal(f.cells.get(2), 'old name');
  assert.equal(f.journals.get('op').state, 'recovery_required');
  f.host.writeCellValue = write;
  restoreJournal(f.host, f.journals.get('op'), false);
  assert.equal(f.journals.get('op').state, 'undone');
  assert.equal(f.cells.get(1), 'old');
});

test('post-sync undo receipt failure does not duplicate inverse business operations', () => {
  const f = fixture();
  f.suggestion.inverse_business_operations = [{ action: 'remove', collection: 'requirements', id: 'own' }];
  applyNextEdit({ ...f, operationId: 'op' });
  f.host.writeMetadata({ ...f.host.readMetadata(), binding: { binding_revision: 4 } });
  const write = f.host.writeJournal;
  f.host.writeJournal = (value) => {
    if (value.state === 'undone') throw new Error('回执写入失败');
    write(value);
  };
  assert.throws(() => restoreJournal(f.host, f.journals.get('op')), /回执/);
  f.host.writeJournal = write;
  restoreJournal(f.host, f.journals.get('op'), false);
  assert.deepEqual(f.host.readMetadata().business.operations, f.suggestion.inverse_business_operations);
});

test('removal undo restores the exact product identity and clears the local tombstone', () => {
  const f = fixture();
  const binding = f.suggestion.line_bindings[0];
  f.host.writeMetadata({ ...f.host.readMetadata(), line_bindings: [binding] });
  f.suggestion.line_bindings = [];
  f.suggestion.removed_lines = [{ ...binding, device_id: 'existing', values: { model: 'old' } }];
  f.suggestion.patches = f.suggestion.patches.map((p) => ({ ...p, after: '' }));
  applyNextEdit({ ...f, operationId: 'remove' });
  assert.equal(f.host.readMetadata().line_bindings.length, 0);
  restoreJournal(f.host, f.journals.get('remove'));
  assert.deepEqual(f.host.readMetadata().line_bindings, [binding]);
  assert.deepEqual(f.host.readMetadata().business.removed_lines, []);
});

test('metadata write failure rolls back every cell and retains explicit outcome', () => {
  const f = fixture();
  const write = f.host.writeMetadata;
  f.host.writeMetadata = (value) => {
    if (value.line_bindings.length) throw new Error('元数据失败');
    write(value);
  };
  assert.throws(() => applyNextEdit({ ...f, operationId: 'op' }), /已恢复.*元数据失败/);
  assert.equal(f.cells.get(1), 'old');
  assert.equal(f.cells.get(2), 'old name');
  assert.equal(f.journals.get('op').state, 'restored');
});

test('second supply undo after sync restores the first local allocation, including receipt retry', () => {
  const f = fixture();
  const existing = { id: 'stock', device_id: 'd', source: 'existing', quantity: '2', evidence: '已确认库存' };
  const first = { ...f.suggestion, patches: [], business_operations: [
    { action: 'supply_set', device_id: 'd', allocations: [existing] },
  ] };
  applyNextEdit({ host: f.host, suggestion: first, operationId: 'first' });
  // This configuration is the HTTP preview of the first local group, not the fixed baseline.
  const { operations, inverse } = rowBusinessOperations({
    configuration: { requirements: [], supply_allocations: [existing] },
    requirementId: 'r', systemId: 's', deviceId: 'd', environmentKey: '', environmentValue: '',
    supply: 'purchase', quantity: '2', evidence: '改为采购', allocationId: 'purchase',
  });
  const second = { ...first, id: 'second', local_revision: 1,
    business_operations: operations, inverse_business_operations: inverse };
  applyNextEdit({ host: f.host, suggestion: second, operationId: 'second' });
  const meta = f.host.readMetadata();
  f.host.writeMetadata({ ...meta, binding: { binding_revision: 2, base_revision: 1 },
    business: { ...meta.business, operations: [] } });
  const write = f.host.writeJournal;
  f.host.writeJournal = (value) => {
    if (value.state === 'undone') throw new Error('回执失败');
    write(value);
  };
  assert.throws(() => restoreJournal(f.host, f.journals.get('second')), /回执失败/);
  f.host.writeJournal = write;
  restoreJournal(f.host, f.journals.get('second'), false);
  assert.deepEqual(f.host.readMetadata().business.operations, [
    { action: 'supply_set', device_id: 'd', allocations: [existing] },
  ]);
  assert.equal(f.host.readMetadata().binding.base_revision, 1);
});

test('old group cannot undo into a new project binding with the same revision', () => {
  const f = fixture();
  f.host.writeMetadata({ ...f.host.readMetadata(), binding: { binding_id: 'old', binding_revision: 1 } });
  applyNextEdit({ ...f, operationId: 'op' });
  f.host.writeMetadata({ ...f.host.readMetadata(), binding: { binding_id: 'new', binding_revision: 1 } });
  assert.throws(() => restoreJournal(f.host, f.journals.get('op')), /其他项目绑定/);
  assert.equal(f.cells.get(1), 'new');
  assert.equal(f.journals.get('op').state, 'applied');
});
