import assert from 'node:assert/strict';
import { test } from 'node:test';

import { headerFingerprint, reconcileLineBindings } from '../src/template.ts';

function line(row, model, quantity = '1') {
  return {
    line_id: `line-${row}`, sheet: '报价表', row, model, name: '服务器', description: '',
    quantity, unit: '台', brand: '', price: null, note: '', section: '', kind: 'hardware',
    variant_id: 'variant', source_id: 'source',
  };
}

test('header fingerprint ignores whitespace and case but detects layout changes', async () => {
  const first = await headerFingerprint([' 产品型号 ', 'QUANTITY']);
  assert.equal(first, await headerFingerprint(['产品 型号', 'quantity']));
  assert.notEqual(first, await headerFingerprint(['产品名称', 'quantity']));
});

test('line reconciliation follows a uniquely moved business row', () => {
  const moved = line(8, 'SERVER-X', '2');
  const bindings = [{
    line_id: 'stable-line', sheet: '报价表', row: 3,
    anchor_fingerprint: ['server-x', '服务器'].join('\0'),
    variant_id: 'variant', source_id: 'source',
  }];
  assert.deepEqual(reconcileLineBindings([moved], bindings), [{ ...bindings[0], row: 8 }]);
});

test('ambiguous duplicate rows are not silently rebound', () => {
  const bindings = [{
    line_id: 'stable-line', sheet: '报价表', row: 3,
    anchor_fingerprint: ['server-x', '服务器'].join('\0'),
    variant_id: 'variant', source_id: 'source',
  }];
  assert.deepEqual(reconcileLineBindings([line(7, 'SERVER-X'), line(8, 'SERVER-X')], bindings), []);
});
