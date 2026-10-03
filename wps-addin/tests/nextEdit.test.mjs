import assert from 'node:assert/strict';
import { test } from 'node:test';
import { nextEditAction } from '../src/nextEditState.ts';
import { WorkbookRowIndex } from '../src/workbookRowIndex.ts';
import { subscribeHostEvent, sheetChange } from '../src/hostEvents.ts';
import { recoverSyncReceipt } from '../src/syncRecovery.ts';
import { deviceIdForLine } from '../src/businessIdentity.ts';

const base = { cell: { sheet: 'quote', row: 3 }, ready: true, composing: false, explicit: false, count: 1,
  suggestion: { patches: [{ sheet: 'quote', row: 3 }], applicable: true, acceptance: 'inline' } };
test('next edit locates offscreen changes and requires preview for quantities', () => {
  assert.equal(nextEditAction(base), 'apply');
  assert.equal(nextEditAction({ ...base, composing: true }), 'native');
  assert.equal(nextEditAction({ ...base, ready: false }), 'native');
  assert.equal(nextEditAction({ ...base, count: 2 }), 'expand');
  assert.equal(nextEditAction({ ...base, cell: { sheet: 'quote', row: 9 } }), 'locate');
  assert.equal(nextEditAction({ ...base, suggestion: { ...base.suggestion, acceptance: 'preview' } }), 'preview');
});

test('row index reads once and refreshes only affected rows, structural edits rebuild', () => {
  let reads = 0; const rows = [];
  const host = { readRows: () => { reads++; return [{ row: 3, values: { model: 'a' } }]; },
    readRow: (_, row) => { rows.push(row); return { row, values: { model: 'changed' } }; } };
  const index = new WorkbookRowIndex(host, { sheet_selector: 'quote' });
  index.read(); index.read(); index.changed({ sheet: 'other', row: 3, rowCount: 1 });
  index.changed({ sheet: 'quote', row: 3, rowCount: 1 }); index.read();
  assert.equal(reads, 1); assert.deepEqual(rows, [3]);
  index.changed({ sheet: 'quote', structural: true }); index.read(); assert.equal(reads, 2);
});

test('host listeners share registration and preserve sheet/range information', () => {
  const handlers = new Map(); let adds = 0, removes = 0, calls = 0;
  const api = { AddApiEventListener: (name, fn) => { adds++; handlers.set(name, fn); },
    RemoveApiEventListener: () => { removes++; } };
  const stop1 = subscribeHostEvent(api, 'SheetChange', () => calls++);
  const stop2 = subscribeHostEvent(api, 'SheetChange', () => calls++);
  handlers.get('SheetChange')(); assert.equal(adds, 1); assert.equal(calls, 2);
  stop1(); assert.equal(removes, 0); stop2(); assert.equal(removes, 1);
  assert.equal(sheetChange({ Name: 'quote' }, { Row: 3, Address: '$3:$3' }).structural, true);
});

test('sync recovery preserves later edits and consumes only submitted business operations', () => {
  const op = { action: 'requirement_put' };
  const metadata = { binding: { binding_id: 'binding' }, line_bindings: [{ line_id: 'row', requirement_id: 'role' }],
    business: { local_revision: 1, operations: [op, { action: 'later' }] },
    pending_sync: { operations: [op], line_bindings: [] } };
  const result = recoverSyncReceipt(metadata, { binding_id: 'binding', base_revision: 4, line_bindings: [{ line_id: 'row', device_id: 'device' }] });
  assert.equal(result.line_bindings[0].requirement_id, 'role');
  assert.deepEqual(result.business.operations, [{ action: 'later' }]);
  assert.equal(result.pending_sync, undefined);
  assert.throws(() => recoverSyncReceipt({ ...metadata, business: { operations: [] } }, { binding_id: 'binding' }), /重排/);
});

test('workbook device identity uses RFC UUID v5 consistently', async () => {
  assert.equal(await deviceIdForLine('binding', 'line'), '6145a2fa-349c-5212-8973-444e41d12ab2');
});
