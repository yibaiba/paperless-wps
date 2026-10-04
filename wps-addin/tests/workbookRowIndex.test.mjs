import test from 'node:test';
import assert from 'node:assert/strict';
import { WorkbookRowIndex } from '../src/workbookRowIndex.ts';

test('a completed group refreshes each affected row once and never reads other sheets', () => {
  const reads = [], cells = new Map([[3, 'old'], [4, 'other']]);
  const row = (number) => ({ sheet: 'quote', row: number, values: { model: cells.get(number) ?? '' } });
  const index = new WorkbookRowIndex({ readRows: () => [row(3), row(4)],
    readRow: (_, number) => { reads.push(number); return row(number); } }, { sheet_selector: 'quote' });
  index.read(); cells.set(3, 'accepted'); cells.delete(4);
  index.refreshRows([{ sheet: 'quote', row: 3 }, { sheet: 'quote', row: 3 },
    { sheet: 'other', row: 99 }, { sheet: 'quote', row: 4 }]);
  assert.deepEqual(reads, [3, 4]);
  assert.deepEqual(index.read(), [row(3)]);
  assert.deepEqual(index.recentChanges(), []);
});

test('undo refresh removes an earlier cached product without relying on host callbacks', () => {
  let product = 'accepted', scans = 0;
  const row = (number) => ({ sheet: 'quote', row: number, values: { model: number === 3 ? product : 'active' } });
  const index = new WorkbookRowIndex({ readRows: () => { scans++; return [row(3), row(8)]; }, readRow: (_, number) => row(number) },
    { sheet_selector: 'quote' });
  index.read(); product = '';
  index.refreshRows([{ sheet: 'quote', row: 3 }]);
  assert.deepEqual(index.read(), [row(8)]);
  assert.equal(scans, 1);
});

test('failed group refresh stays stale until a query retries every unread row', () => {
  let fail = true;
  const reads = [], row = (number, model) => ({ sheet: 'quote', row: number, values: { model } });
  const index = new WorkbookRowIndex({ readRows: () => [row(3, 'old-A'), row(4, 'old-B')],
    readRow: (_, number) => { reads.push(number); if (fail) throw new Error('host read failed'); return row(number, ''); } },
  { sheet_selector: 'quote' });
  index.read();
  assert.throws(() => index.refreshRows([{ sheet: 'quote', row: 3 }, { sheet: 'quote', row: 4 }]), /host read failed/);
  assert.throws(() => index.read(), /host read failed/);
  fail = false;
  assert.deepEqual(index.read(), []);
  assert.deepEqual(reads, [3, 3, 3, 4]);
});

test('a failed pasted range cannot leave later rows looking fresh on retry', () => {
  let fail = true;
  const row = (number, quantity) => ({ sheet: 'quote', row: number, values: { model: `M${number}`, quantity } });
  const index = new WorkbookRowIndex({ readRows: () => [row(3, '1'), row(4, '1')],
    readRow: (_, number) => { if (fail && number === 3) throw new Error('host read failed'); return row(number, '2'); } },
  { sheet_selector: 'quote' });
  index.read();
  assert.throws(() => index.changed({ sheet: 'quote', row: 3, rowCount: 2 }, { historyKey: 'current' }), /host read failed/);
  fail = false;
  assert.deepEqual(index.read().map((r) => r.values.quantity), ['2', '2']);
  assert.deepEqual(index.recentChanges().map((e) => [e.before.values.quantity, e.after.values.quantity, e.historyKey]),
    [['1', '2', 'current'], ['1', '2', 'current']]);
});
