import assert from 'node:assert/strict';
import { test } from 'node:test';

test('WPS adapter addresses cells through the collection Item method', async () => {
  const storage = new Map();
  let selectionMoved = false;
  const values = new Map([
    ['1:1', { Text: '产品型号', Formula: '', MergeCells: false }],
    ['2:1', { Text: 'OLD', Formula: '', MergeCells: false, Value2: 'OLD' }],
    ['2:2', { Text: '3,000', Formula: '', MergeCells: false, Value2: 3000 }],
    ['2:3', { Text: '¥12.00', Formula: '', MergeCells: false, Value2: 12 }],
  ]);
  const sheet = {
    Name: '报价表',
    UsedRange: { Row: 1, Rows: { Count: 2 }, Columns: { Count: 1 } },
    Cells: { Item: (row, column) => values.get(`${row}:${column}`) },
  };
  globalThis.window = {
    localStorage: {
      getItem: (key) => storage.get(`local:${key}`),
      setItem: (key, value) => storage.set(`local:${key}`, String(value)),
    },
    Application: {
      ActiveWorkbook: { Worksheets: { Count: 1, Item: () => sheet } },
      ActiveSheet: sheet,
      PluginStorage: {
        getItem: (key) => storage.get(key),
        setItem: (key, value) => storage.set(key, String(value)),
      },
      Selection: {
        Offset: (row, column) => ({
          Select: () => { selectionMoved = row === 1 && column === 0; },
        }),
      },
    },
  };
  const { WpsHostAdapter } = await import('../src/host.ts');
  const host = new WpsHostAdapter();
  const row = host.readRow({ sheet_selector: '报价表', field_columns: { quantity: 2, price: 3 } }, 2);
  assert.equal(row.values.quantity, '3000');
  assert.equal(row.values.price, '12');
  assert.equal(row.values.price, host.readCell({ sheet: '报价表', row: 2, column: 3 }).value);
  assert.deepEqual(host.readHeader('报价表', 1), ['产品型号']);
  host.writeCandidate({
    sheet_selector: '报价表', managed_fields: ['model'], field_columns: { model: 1 },
  }, 2, { model: 'NEW' });
  assert.equal(values.get('2:1').Value2, 'NEW');
  host.moveSelection(1, 0);
  assert.equal(selectionMoved, true);
});
