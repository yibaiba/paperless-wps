import test from 'node:test';
import assert from 'node:assert/strict';
import { mappingValues, quantityValues, reconciliationRows, roleSuggestion, quantityDescription } from '../src/features/configuration/knowledge/reconciliation.ts';

const definition = { id: 'windows', revision: 2, name: 'Windows', roles: [{ id: 'server', name: '服务端' }] };
const rule = { id: 'k', revision: 3, name: '旧关系', kind: 'accessory', system: '旧系统', role: '服务端', system_definition_id: '', role_id: '', status: 'confirmed',
  quantity_review: 'unreviewed', quantity_evidence: '', selector: { variant_ids: ['a'], exclude_variant_ids: ['b'] },
  conditions: [{ field: 'project.os' }], activation_conditions: [{ field: 'project.feature' }], evidence: '产品原文', evidence_refs: [{ source_id: 's' }],
  migration_source: { id: 'legacy' }, identity_mapping: { historical_reference: 'old-map' }, target_variant_ids: [], factor: null };

test('explicit mapping preserves conditions, scope, original evidence and quantity state', () => {
  const before = structuredClone(rule);
  assert.equal(roleSuggestion(rule, definition).id, 'server');
  assert.throws(() => mappingValues({ rule, definition, actor: '甲', evidence: '人工核对', roleId: '' }), /请选择/);
  const mapped = mappingValues({ rule, definition, roleId: 'server', actor: '甲', evidence: '人工核对归属' });
  assert.equal(mapped.system_definition_id, 'windows'); assert.equal(mapped.role_id, 'server');
  for (const key of ['status', 'quantity_review', 'selector', 'conditions', 'activation_conditions', 'evidence', 'evidence_refs', 'migration_source']) assert.deepEqual(mapped[key], before[key]);
  assert.equal(mapped.identity_mapping.historical_reference, 'old-map');
  assert.equal(mapped.identity_mapping.previous_system, '旧系统');
  assert.equal(mapped.identity_mapping.definition_revision, 2);
  assert.deepEqual(rule, before);
});

test('same names in another stable system are never suggested or silently merged', () => {
  assert.equal(roleSuggestion({ ...rule, system_definition_id: 'linux', role_id: 'server' }, definition), undefined);
  assert.equal(roleSuggestion(rule, { ...definition, roles: [...definition.roles, { id: 'other', name: '服务端' }] }), undefined);
  assert.throws(() => mappingValues({ rule: { ...rule, kind: 'sharing' }, definition, roleId: 'server', actor: '甲', evidence: '依据' }), /共享/);
});

test('quantity editor changes only its owned fields without defaulting unknown formulas', () => {
  const edited = quantityValues(rule, { factor: null, quantity_review: 'unreviewed', quantity_evidence: '仍缺容量', status: 'draft', conditions: [], need_key: 'changed', target_variant_ids: ['a'] });
  assert.equal(edited.status, 'confirmed'); assert.deepEqual(edited.conditions, rule.conditions);
  assert.equal(edited.need_key, undefined); assert.equal(edited.factor, null);
  assert.equal(edited.quantity_evidence, '仍缺容量'); assert.deepEqual(edited.evidence_refs, rule.evidence_refs);
  assert.equal(quantityDescription(edited), '数量口径待补');
});

test('current relation and pinned package revisions remain separate, absent current records are explicit', () => {
  const bundle = { rules: [{ ...rule, revision: 1 }, { ...rule, id: 'missing' }] };
  const before = structuredClone(bundle);
  const rows = reconciliationRows(bundle, [rule]);
  assert.equal(rows[0].fixed.revision, 1); assert.equal(rows[0].current.revision, 3);
  assert.equal(rows[1].current, undefined); assert.deepEqual(bundle, before);
});
