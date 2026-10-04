import test from 'node:test';
import assert from 'node:assert/strict';
import { assertInlineSession, writeInlineInput } from '../src/workbookSession.ts';

function fixture() {
  const context = { workbook_key: 'quote.xlsx', binding_id: 'project', session_id: 'old-cell',
    profile: { header_row: 1, sheet_selector: 'q', managed_fields: ['name'], field_columns: { name: 2 } },
    cell: { sheet: 'q', row: 3, column: 2, formula: '', merged: false } };
  let current = context, writes = 0;
  return { context, host: { workbookKey: () => 'quote.xlsx', readMetadata: () => ({ binding: { binding_id: 'project' } }),
    inlineContext: () => current, writeCellValue: () => { writes++; } },
  switchTo: (value) => { current = value; }, writes: () => writes };
}

test('late inline results cannot enter a replaced or closed cell session in the same workbook', () => {
  for (const current of [null, { session_id: 'new-cell' }]) {
    const f = fixture();
    assertInlineSession(f.host, f.context);
    f.switchTo(current);
    assert.throws(() => assertInlineSession(f.host, f.context), /补全单元格已切换/);
  }
});

test('a queued input event cannot write the previous cell after the host changes its session', () => {
  const f = fixture();
  f.switchTo({ session_id: 'new-cell' });
  assert.throws(() => writeInlineInput({ ...f, value: '旧输入' }), /补全单元格已切换/);
  assert.equal(f.writes(), 0);
});

test('an active input session continues to write normally', () => {
  const f = fixture();
  writeInlineInput({ ...f, value: '当前输入' });
  assert.equal(f.writes(), 1);
});
