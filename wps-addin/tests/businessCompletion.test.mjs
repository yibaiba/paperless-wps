import test from 'node:test';
import assert from 'node:assert/strict';
import { businessCompletionSelection, businessCompletionGhost, resolvedBusinessChoice } from '../src/businessCompletion.ts';
import { isProductInputCell } from '../src/productInput.ts';
import { writeInlineInput } from '../src/workbookSession.ts';
import { nextEditAction } from '../src/nextEditState.ts';
import { nextEditNotice } from '../src/nextEditPresentation.ts';

const cell = { sheet: '报价表', row: 4, column: 2, formula: '', merged: false };
const candidate = (id) => ({ id, label: '服务器', line_bindings: [], applicable: true, acceptance: 'inline',
  patches: [{ ...cell, field: 'name', before: '', after: '服务器' }] });
const result = { items: [candidate('alternative'), candidate('primary')],
  primary_suggestion_id: 'primary', decision: { status: 'ready' } };

test('overlay selects the actual primary, not the first lower-ranked alternative', () => {
  assert.deepEqual(businessCompletionSelection({ result, cell, query: '服' }), { index: 1, expanded: false });
});

test('a malformed primary ID is surfaced instead of accepting the first alternative', () => {
  assert.throws(() => businessCompletionSelection({ result: { ...result, primary_suggestion_id: 'missing' },
    cell, query: '服' }), /主建议 ID 不存在/);
});

test('ambiguous or non-prefix candidates are visible choices, not hidden gray-text accepts', () => {
  const options = { result, cell, query: '服' };
  assert.equal(businessCompletionSelection({ ...options,
    result: { ...result, decision: { status: 'choice_required' } } }).expanded, true);
  assert.equal(businessCompletionSelection({ ...options, query: '务器' }).expanded, true);
  assert.equal(businessCompletionSelection({ ...options,
    result: { ...result, primary_suggestion_id: null } }).expanded, true);
});

test('only an acceptable edit here renders gray text; off-row and preview changes do not', () => {
  const options = { result, index: 1, cell, query: '服', ready: true, explicit: false };
  assert.deepEqual(businessCompletionGhost(options), { prefix: '服', suffix: '务器' });
  assert.deepEqual(businessCompletionGhost({ ...options, query: '' }), { prefix: '', suffix: '服务器' });
  assert.equal(businessCompletionGhost({ ...options, ready: false }), null);
  assert.equal(businessCompletionGhost({ ...options, cell: { ...cell, row: 7 } }), null);
  for (const change of [{ acceptance: 'preview' }, { applicable: false }]) {
    assert.equal(businessCompletionGhost({ ...options,
      result: { ...result, items: result.items.map((item) => ({ ...item, ...change })) } }), null);
  }
});

test('header, quantity, notes, unmanaged columns and protected cells cannot be product input', () => {
  const profile = { sheet_selector: '报价表', header_row: 1, field_columns: { model: 1, name: 2, quantity: 3, note: 4 },
    managed_fields: ['model', 'name'] };
  let writes = 0;
  const host = { workbookKey: () => 'quote.xlsx', readMetadata: () => ({}),
    inlineContext: () => ({ session_id: 'protected-input' }), writeCellValue: () => { writes++; } };
  for (const target of [{ ...cell, row: 1 }, { ...cell, column: 3 }, { ...cell, column: 4 },
    { ...cell, column: 9 }, { ...cell, formula: '=SUM(A1:A3)' }, { ...cell, merged: true }, { ...cell, sheet: '其他表' }]) {
    assert.equal(isProductInputCell(profile, target), false);
    assert.throws(() => writeInlineInput({ host,
      context: { workbook_key: 'quote.xlsx', session_id: 'protected-input', profile, cell: target }, value: '不可写' }), /插件管理/);
  }
  assert.equal(writes, 0);
  assert.equal(isProductInputCell({ ...profile, managed_fields: ['model'] }, cell), false);
  assert.equal(isProductInputCell(profile, cell), true);
});

test('quantity locations remain previewable, never writable as product input', () => {
  const target = { ...cell, column: 3 };
  const suggestion = { ...candidate('quantity'), acceptance: 'preview',
    patches: [{ ...target, field: 'quantity', before: '1', after: '4' }] };
  const options = { suggestion, cell: target, query: '', ready: true,
    composing: false, explicit: false, count: 1 };
  assert.equal(nextEditAction(options), 'preview');
  assert.match(nextEditNotice(options).action, /Tab 查看修改预览/);
  assert.match(nextEditNotice(options).target, /数量：4/);
  assert.equal(nextEditAction({ ...options, cell: { ...cell, row: 5 } }), 'locate');
});

test('resolved choices share apply, preview and locate rules rather than always opening a preview', () => {
  const item = candidate('chosen');
  const options = { result: { items: [item] }, cell, query: '务器' };
  assert.equal(resolvedBusinessChoice(options).action, 'apply');
  assert.equal(resolvedBusinessChoice({ ...options, cell: { ...cell, row: 5 } }).action, 'locate');
  for (const change of [{ applicable: false }, { acceptance: 'preview' }]) {
    assert.equal(resolvedBusinessChoice({ ...options, result: { items: [{ ...item, ...change }] } }).action, 'preview');
  }
  assert.equal(resolvedBusinessChoice({ ...options,
    result: { items: [item, candidate('another')], decision: { status: 'choice_required' } } }).action, 'expand');
  assert.equal(resolvedBusinessChoice({ ...options, result: { items: [] } }).action, 'native');
});
