import test from 'node:test';
import assert from 'node:assert/strict';
import { nextEditAction } from '../src/nextEditState.ts';
import { verifiedEditTarget } from '../src/nextEditTarget.ts';
import { acceptedEdit, undoneEdit, observedQuantityEdits, recentHistoryKey, dismissedMetadata } from '../src/recentBusinessEdits.ts';
import { WorkbookRowIndex } from '../src/workbookRowIndex.ts';
import { rowAnchor } from '../src/workbook.ts';
import { nextEditNotice } from '../src/nextEditPresentation.ts';

const suggestion = { id: 's', acceptance: 'inline', applicable: true, context_fingerprint: 'context',
  local_revision: 3, patches: [{ sheet: 'quote', row: 8, column: 2, field: 'name', before: '', after: '硬件' }],
  line_bindings: [{ line_id: 'line', device_id: 'device', requirement_id: 'role' }],
  semantic_action_id: 'action', business_context_fingerprint: 'business',
  changes: [{ kind: 'devices', id: 'device', before: null, after: { quantity: '1' } }] };
const target = { sheet: 'quote', row: 8, column: 2, field: 'name', expected_value: '',
  line_id: null, local_revision: 3, context_fingerprint: 'context' };

test('primary can be accepted with lower alternatives; real ambiguity still expands', () => {
  const options = { suggestion, cell: target, ready: true, composing: false, explicit: false,
    count: 2, primarySuggestionId: 's', decision: { status: 'ready' } };
  assert.equal(nextEditAction(options), 'apply');
  assert.equal(nextEditAction({ ...options, decision: { status: 'choice_required' } }), 'expand');
  assert.equal(nextEditAction({ ...options, composing: true }), 'native');
  assert.equal(nextEditAction({ ...options, ready: false }), 'native');
  assert.equal(nextEditAction({ ...options, target: { ...target, column: 4 } }), 'locate');
});

test('next target validates version original value and identity without selecting or writing', () => {
  let value = '', revision = 3;
  const host = { businessRevision: () => revision, readMetadata: () => ({ line_bindings: [] }),
    readCell: (cell) => ({ ...cell, value, formula: '', merged: false }) };
  const result = { items: [suggestion], primary_suggestion_id: 's', next_target: target,
    local_revision: 3, context_fingerprint: 'context' };
  assert.equal(verifiedEditTarget({ host, result, suggestion }).row, 8);
  value = '手改'; assert.throws(() => verifiedEditTarget({ host, result, suggestion }), /原值/);
  value = ''; revision = 4; assert.throws(() => verifiedEditTarget({ host, result, suggestion }), /过期/);
  revision = 3;
  assert.throws(() => verifiedEditTarget({ host, suggestion,
    result: { ...result, next_target: { ...target, line_id: 'moved' } } }), /已移动/);
});

test('quantity target notice shows its actual proposed value, not the product name', () => {
  const quantity = { ...target, column: 4, field: 'quantity' };
  const item = { ...suggestion, patches: [{ ...quantity, before: '1', after: '4' }],
    line_bindings: [{ confirmed_values: { name: '硬件' } }] };
  const notice = nextEditNotice({ suggestion: item, target: quantity, cell: target, query: '' });
  assert.equal(notice.target, 'quote · 第 8 行 · 数量：4');
});

test('accept and undo retain stable action context and ordered structured changes', () => {
  const edit = acceptedEdit({ suggestion, operationId: 'op', previous: [{ sequence: 6 }] });
  assert.equal(edit.sequence, 7);
  assert.equal(edit.line_id, 'line');
  assert.deepEqual(edit.changes, suggestion.changes);
  const undo = undoneEdit({ operation_id: 'op', suggestion_id: 's', ...suggestion }, [edit]);
  assert.equal(undo.sequence, 8);
  assert.equal(undo.semantic_action_id, 'action');
  assert.equal(undo.business_context_fingerprint, 'business');
});

test('explicit dismissal invalidates old previews and cache keys without changing business facts', () => {
  const metadata = { line_bindings: [], business: { local_revision: 3, operations: [], recent_edits: [] } };
  const next = dismissedMetadata({ metadata, suggestion, operationId: 'dismiss' });
  assert.equal(next.business.local_revision, 4);
  assert.equal(metadata.business.local_revision, 3);
  assert.equal(next.business.operations, metadata.business.operations);
  assert.equal(next.business.recent_edits[0].kind, 'dismiss');
  assert.throws(() => verifiedEditTarget({ suggestion, result: { local_revision: 3 },
    host: { businessRevision: () => next.business.local_revision } }), /过期/);
});

test('committed quantities carry row identity; input text and earlier events do not masquerade as edits', () => {
  let row = { sheet: 'quote', row: 8, values: { name: '硬件', quantity: '1' } };
  const metadata = { line_bindings: [{ line_id: 'line', device_id: 'device', sheet: 'quote', row: 8,
    anchor_fingerprint: rowAnchor(row), confirmed_values: row.values }], business: { recent_edits: [] } };
  const index = new WorkbookRowIndex({ readRows: () => [row], readRow: () => row }, { sheet_selector: 'quote' });
  const event = { sheet: 'quote', row: 8, rowCount: 1, structural: false };
  index.read(); row = { ...row, values: { ...row.values, quantity: '2' } };
  index.changed(event, { historyKey: recentHistoryKey(metadata) });
  const [edit] = observedQuantityEdits(index, metadata);
  assert.equal(edit.line_id, 'line');
  assert.deepEqual(edit.changes[0], { kind: 'devices', id: 'device', before: { quantity: '1' }, after: { quantity: '2' } });
  metadata.business.recent_edits.push({ operation_id: 'newer', kind: 'accept', sequence: 1 });
  assert.deepEqual(observedQuantityEdits(index, metadata), []);
  row = { ...row, values: { ...row.values, name: '正在输' } };
  index.changed(event, { historyKey: recentHistoryKey(metadata) });
  assert.deepEqual(observedQuantityEdits(index, metadata), []);
  index.changed({ ...event, structural: true });
  assert.deepEqual(index.recentChanges(), []);
});

test('a later note edit preserves the real quantity change without changing its business order', () => {
  const rows = new Map([8, 9].map((row) => [row, { sheet: 'quote', row, values: { name: `硬件${row}`, quantity: '1' } }]));
  const metadata = { line_bindings: [...rows.values()].map((row) => ({ line_id: `line-${row.row}`,
    device_id: `device-${row.row}`, sheet: row.sheet, row: row.row,
    anchor_fingerprint: rowAnchor(row), confirmed_values: row.values })), business: { recent_edits: [] } };
  const index = new WorkbookRowIndex({ readRows: () => [...rows.values()], readRow: (_, row) => rows.get(row) }, { sheet_selector: 'quote' });
  index.read();
  const edit = (row, fields) => {
    rows.set(row, { ...rows.get(row), values: { ...rows.get(row).values, ...fields } });
    index.changed({ sheet: 'quote', row, rowCount: 1 }, { historyKey: recentHistoryKey(metadata) });
  };
  edit(8, { quantity: '2' }); edit(9, { quantity: '3' }); edit(8, { note: '客户新增说明' });
  assert.deepEqual(observedQuantityEdits(index, metadata).map((e) => [e.row, e.changes[0].before.quantity, e.changes[0].after.quantity]),
    [[8, '1', '2'], [9, '1', '3']]);
  edit(8, { quantity: '4' });
  assert.deepEqual(observedQuantityEdits(index, metadata).map((e) => e.row), [9, 8]);
  edit(8, { quantity: '1' });
  assert.deepEqual(observedQuantityEdits(index, metadata).map((e) => e.row), [9]);
});
