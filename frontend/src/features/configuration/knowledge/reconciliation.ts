import type { Knowledge, KnowledgePackage, SystemDefinition } from '../types';

export function reconciliationRows(bundle: KnowledgePackage, knowledge: Knowledge[]) {
  const current = new Map(knowledge.map(rule => [rule.id, rule]));
  return bundle.rules.map(fixed => ({ fixed, current: current.get(fixed.id) }));
}

export function roleSuggestion(rule: Knowledge, definition: SystemDefinition) {
  if (rule.system_definition_id && rule.system_definition_id !== definition.id) return undefined;
  const matches = definition.roles.filter(role => rule.role_id
    ? rule.system_definition_id === definition.id && role.id === rule.role_id
    : role.name === rule.role);
  return matches.length === 1 ? matches[0] : undefined;
}

export function mappingValues({ rule, definition, roleId, actor, evidence }: {
  rule: Knowledge; definition: SystemDefinition; roleId: string; actor: string; evidence: string;
}) {
  if (!actor.trim() || !evidence.trim()) throw new Error('请填写维护人和归属核对依据');
  if (rule.kind === 'sharing') throw new Error('共享关系涉及多个系统角色，请使用高级编辑逐项核对');
  const role = definition.roles.find(item => item.id === roleId);
  if (!role) throw new Error('请选择本包固定定义中的角色');
  return { ...rule, system_definition_id: definition.id, system: definition.name, role_id: role.id, role: role.name,
    actor: actor.trim(), identity_mapping: { ...rule.identity_mapping, actor: actor.trim(), evidence: evidence.trim(),
      definition_revision: definition.revision, previous_system: rule.system, previous_role: rule.role,
      previous_system_definition_id: rule.system_definition_id, previous_role_id: rule.role_id, previous_revision: rule.revision } };
}

// A quantity-only edit cannot replace status, applicability, allocation or provenance.
const quantityFields = ['target_variant_ids', 'calculation_scope', 'quantity_source', 'quantity_key', 'quantity_unit',
  'mode', 'factor', 'quantity_review', 'quantity_evidence', 'evidence_refs', 'actor'] as const;
export function quantityValues(rule: Knowledge, values: Partial<Knowledge>): Knowledge {
  return { ...rule, ...Object.fromEntries(quantityFields.filter(key => key in values).map(key => [key, values[key]])) };
}

export function quantityDescription(rule: Knowledge) {
  if (!rule.calculation_scope || !rule.mode || rule.factor == null) return '数量口径待补';
  const scope = { device: '每个设备', system: '每个系统', room: '每个房间', project: '整个项目' }[rule.calculation_scope];
  const input = rule.quantity_source === 'environment' ? `需求参数 ${rule.quantity_key || '待选'}${rule.quantity_unit ? `（${rule.quantity_unit}）` : ''}` : '范围内设备数量';
  const formula = { per_unit: `${input} × ${rule.factor}`, per_capacity: `${input} ÷ ${rule.factor}，向上取整`, per_group: `固定 ${rule.factor}` }[rule.mode];
  return `${scope}：${formula}`;
}
