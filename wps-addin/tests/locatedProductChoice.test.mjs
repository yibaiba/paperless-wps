import test from 'node:test';
import assert from 'node:assert/strict';
import { locatedProductChoice, locatedChoiceRequest } from '../src/locatedProductChoice.ts';

const context = { workbook_key: 'quote.xlsx', binding_id: 'project', session_id: 'new-session', nonce: 2,
  profile: { id: 'profile', revision: 4 }, cell: { sheet: '报价表', row: 8, column: 2, value: '' } };
const binding = { sheet: '报价表', row: 8, variant_id: 'B', source_id: 'source-B' };
const suggestion = { local_revision: 3, line_bindings: [binding] };
const choice = locatedProductChoice({ context, suggestion });

test('located choice retains concrete variant and source for a fresh target preview', () => {
  assert.deepEqual(locatedChoiceRequest({ choice, context, localRevision: 3, query: '' }),
    { selected_variant_id: 'B', selected_source_id: 'source-B' });
  assert.equal('suggestion' in choice, false);
});

test('located choice cannot follow a new query, revision, session, file, binding, template or cell', () => {
  const options = { choice, context, localRevision: 3, query: '' };
  for (const change of [{ query: '软件' }, { localRevision: 4 }, { choice: undefined }]) {
    assert.equal(locatedChoiceRequest({ ...options, ...change }), undefined);
  }
  for (const change of [{ workbook_key: 'copy.xlsx' }, { binding_id: 'other-project' },
    { session_id: 'other-session' }, { nonce: 3 }, { profile: { ...context.profile, id: 'other' } },
    { profile: { ...context.profile, revision: 5 } },
    ...[{ sheet: '其他表' }, { row: 9 }, { column: 3 }, { value: '手工改动' }].map((cell) => ({ cell: { ...context.cell, ...cell } }))]) {
    assert.equal(locatedChoiceRequest({ ...options, context: { ...context, ...change } }), undefined);
  }
});

test('target binding is selected by location, never the first binding of a cross-row group', () => {
  assert.deepEqual(locatedProductChoice({ context, suggestion: { ...suggestion,
    line_bindings: [{ ...binding, row: 7, variant_id: 'A' }, binding] } }), choice);
  for (const line_bindings of [[], [{ ...binding, row: 7 }], [binding, binding], [{ ...binding, source_id: '' }]]) {
    assert.equal(locatedProductChoice({ context, suggestion: { ...suggestion, line_bindings } }), undefined);
  }
  assert.equal(locatedProductChoice({ context: null, suggestion }), undefined);
});
