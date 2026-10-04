import test from 'node:test';
import assert from 'node:assert/strict';
import { completionMode, decisionText, issueText } from '../src/businessContextPresentation.ts';
import { availableProductTarget } from '../src/businessTargets.ts';
import { WorkbookRowIndex } from '../src/workbookRowIndex.ts';

test('mode and unknown decision do not pretend to understand a legacy workbook', () => {
  assert.equal(completionMode(1), '基础产品补全');
  assert.equal(completionMode(2), '业务上下文推荐');
  assert.match(decisionText(), /未提供/);
  assert.match(decisionText({ status: 'confirmation_required', reason_code: 'evidence_required' }), /未确认/);
  assert.match(decisionText({ status: 'satisfied', reason_code: 'requirements_satisfied' }), /受检范围/);
  assert.match(decisionText({ status: 'ready', reason_code: 'exact_input' }), /明确输入/);
});

test('issues retain actionable row and business field locations', () => {
  const text = issueText({ message: '授权数量待确认', sheet: '报价', row: 6, field: 'licenses' });
  assert.match(text, /报价 · 第 6 行 · 字段 licenses/);
  assert.match(text, /授权数量待确认/);
});

test('new products use the nearest safe business row, including above the current cell', () => {
  const reads = [], profile = { sheet_selector: 'q', managed_fields: ['model', 'name'] };
  const row = (number) => ({ sheet: 'q', row: number, values: {}, formula_fields: number === 7 ? ['quantity'] : [], merged_fields: [] });
  const index = new WorkbookRowIndex({ readRows: () => [], readRow: (_, number) => { reads.push(number); return row(number); } }, profile);
  index.read();
  const options = { scope: { sheet: 'q', start_row: 3, end_row: 8 }, activeRow: 6, profile,
    occupied: new Set([6]), readRow: (number) => index.peek(number) };
  assert.equal(availableProductTarget(options).row, 5);
  assert.equal(availableProductTarget(options).row, 5);
  assert.deepEqual(reads, [7, 5]); // Cached blank/formula rows do not reread the host per keystroke.
  index.changed({ sheet: 'q', row: 5, rowCount: 1, structural: false });
  assert.deepEqual(reads, [7, 5, 5]);
  assert.equal(availableProductTarget({ ...options, activeRow: 8, occupied: new Set([3, 4, 5, 6, 7, 8]) }), undefined);
});
