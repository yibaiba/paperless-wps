import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeQuickEdit, copyKnowledge, matchingConfigurations, requiresAdvanced } from '../src/features/configuration/knowledge/quickEdit.ts';

test('simple edit preserves non-owned conditions, selector exclusions and provenance', () => {
  const original = { id: 'k', revision: 4, selector: { variant_ids: ['a'], category: 'server', series: ['x'], exclude_variant_ids: ['b'] },
    conditions: [{ field: 'project.os' }], activation_conditions: [{ field: 'project.mode' }], evidence_refs: [{ source_id: 's' }], migration_source: { id: 'legacy' } };
  const result = mergeQuickEdit(original, { name: 'new', selector: { variant_ids: ['a', 'b'] } });
  assert.deepEqual(result.selector.exclude_variant_ids, ['b']);
  for (const key of ['conditions', 'activation_conditions', 'evidence_refs', 'migration_source']) assert.deepEqual(result[key], original[key]);
  assert.equal(requiresAdvanced(original), true);
  const copies = copyKnowledge({ ...original, status: 'confirmed', quantity_review: 'confirmed', name: 'old' });
  assert.equal(copies.status, 'draft'); assert.equal(copies.quantity_review, 'unreviewed'); assert.equal(copies.id, undefined);
});
test('coverage uses configuration identities and excludes same-model alternatives', () => {
  const variants = ['a','b','c'].map(id => ({ id, product: { model: 'same', category: 'server' }, series: ['x'] }));
  const scope = { selector: { variant_ids: ['a','b'], exclude_variant_ids: ['b'], category: '', series: [] } };
  assert.deepEqual(matchingConfigurations(scope, variants).map(v => v.id), ['a']);
});
