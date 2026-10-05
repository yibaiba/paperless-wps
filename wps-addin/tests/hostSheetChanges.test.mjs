import assert from 'node:assert/strict';
import { test } from 'node:test';
import { WpsHostAdapter } from '../src/host.ts';

test('host revision advances once per event, not once per subscribed component', () => {
  const values = new Map(); const storage = { getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)), removeItem: (key) => values.delete(key) };
  let listener, adds = 0, removes = 0;
  globalThis.window = { Application: { ActiveWorkbook: { FullName: 'isolated.xlsx' },
    ApiEvent: { AddApiEventListener: (_, value) => { listener = value; adds++; },
      RemoveApiEventListener: () => { removes++; } } }, localStorage: storage };
  try {
    const host = new WpsHostAdapter(); const calls = [];
    const first = host.onSheetChange((event) => calls.push(event.row));
    const second = host.onSheetChange((event) => calls.push(event.row));
    listener({ Name: 'q' }, { Row: 4, Column: 1, Rows: { Count: 1 }, Columns: { Count: 1 }, Address: '$A$4' });
    assert.deepEqual(calls, [4, 4]);
    assert.equal(values.get('presales_edit_epoch:isolated.xlsx'), '1');
    assert.equal(adds, 1);
    first(); assert.equal(removes, 0); second(); assert.equal(removes, 1);
  } finally { delete globalThis.window; }
});
