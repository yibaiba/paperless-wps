import type { Configuration, Deployment } from '../../types';

export type Operation = Record<string, unknown> & { action: string };
const equal = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const deviceInput = ({ source_snapshot, variant_snapshot, origin_suggestion, generated_origin, ...value }: Deployment) => {
  void source_snapshot; void variant_snapshot; void origin_suggestion; void generated_origin; return value;
};

/** Forms express intent locally; the server alone validates and applies these commands. */
export function configurationOperations(before: Configuration, after: Configuration): Operation[] {
  const operations: Operation[] = [];
  for (const collection of ['rooms', 'systems', 'devices', 'requirements'] as const) {
    const old = new Map(before[collection].map((v) => [v.id, v]));
    const action = { rooms: 'room_put', systems: 'system_put', requirements: 'requirement_put', devices: 'device_put' }[collection];
    for (const value of after[collection]) {
      const previous = old.get(value.id);
      if (equal(previous, value)) continue;
      if (collection !== 'devices') { operations.push({ action, value }); continue; }
      const next = deviceInput(value as Deployment);
      const prev = previous ? deviceInput(previous as Deployment) : undefined;
      if (prev && equal({ ...prev, quantity: next.quantity, note: next.note }, next)) {
        operations.push({ action: 'device_patch', device_id: value.id,
          ...(prev.quantity !== next.quantity ? { quantity: next.quantity } : {}),
          ...(prev.note !== next.note ? { note: next.note } : {}) });
      } else if (!equal(prev, next)) operations.push({ action, value: next });
    }
  }
  for (const collection of ['requirements', 'devices', 'systems', 'rooms'] as const) {
    const ids = new Set(after[collection].map((v) => v.id));
    for (const item of before[collection]) if (!ids.has(item.id)) operations.push({ action: 'remove', collection, id: item.id });
  }
  for (const device of after.devices) {
    const allocations = (after.supply_allocations ?? []).filter((a) => a.device_id === device.id);
    if (!equal(allocations, (before.supply_allocations ?? []).filter((a) => a.device_id === device.id))) {
      operations.push({ action: 'supply_set', device_id: device.id, allocations });
    }
  }
  for (const choice of after.accessory_choices ?? []) {
    if (!equal(choice, before.accessory_choices?.find((c) => c.demand_id === choice.demand_id))) {
      operations.push({ action: 'accessory_choice', demand_id: choice.demand_id, selected: choice.selected });
    }
  }
  for (const choice of before.accessory_choices ?? []) {
    if (!after.accessory_choices?.some((c) => c.demand_id === choice.demand_id)) operations.push({ action: 'accessory_choice_clear', demand_id: choice.demand_id });
  }
  for (const allocation of before.accessory_allocations) {
    if (!equal(allocation, after.accessory_allocations.find((a) => a.id === allocation.id)) && after.devices.some((d) => d.id === allocation.device_id)) {
      operations.push({ action: 'accessory_remove', allocation_id: allocation.id });
    }
  }
  for (const allocation of after.accessory_allocations) {
    if (!equal(allocation, before.accessory_allocations.find((a) => a.id === allocation.id))) operations.push({ action: 'accessory_link', value: allocation });
  }
  for (const allocation of before.included_allocations ?? []) {
    if (!equal(allocation, after.included_allocations?.find((a) => a.id === allocation.id)) && after.devices.some((d) => d.id === allocation.device_id)) {
      operations.push({ action: 'included_remove', allocation_id: allocation.id });
    }
  }
  for (const allocation of after.included_allocations ?? []) {
    if (!equal(allocation, before.included_allocations?.find((a) => a.id === allocation.id))) operations.push({ action: 'included_link', value: allocation });
  }
  if (!equal(before.quotation, after.quotation)) operations.push({ action: 'quotation_replace', value: after.quotation ?? null });
  if (after.actor.trim() && after.evidence.trim() && (before.actor !== after.actor || before.evidence !== after.evidence)) operations.push({ action: 'author_set', actor: after.actor, evidence: after.evidence });
  if (before.drawing_xml !== after.drawing_xml) operations.push({ action: 'drawing_set', xml: after.drawing_xml });
  const productRefresh = after.devices.some((d) => { const previous = before.devices.find((p) => p.id === d.id); return previous && previous.variant_id === d.variant_id && previous.variant_snapshot && d.variant_snapshot && (previous.variant_snapshot.revision !== d.variant_snapshot.revision || previous.variant_snapshot.product.revision !== d.variant_snapshot.product.revision); });
  if (productRefresh || before.knowledge_snapshot_id !== after.knowledge_snapshot_id || before.definition_snapshot_id !== after.definition_snapshot_id || before.calculation_version !== after.calculation_version) {
    operations.push({ action: 'knowledge_refresh', upgrade: after.calculation_version === 3,
      expected_knowledge_snapshot_id: after.knowledge_snapshot_id, expected_definition_snapshot_id: after.definition_snapshot_id,
      expected_product_revisions: Object.fromEntries(after.devices.filter((d) => d.variant_snapshot).map((d) => [d.variant_snapshot!.product.id, d.variant_snapshot!.product.revision])),
      expected_variant_revisions: Object.fromEntries(after.devices.filter((d) => d.variant_snapshot).map((d) => [d.variant_id, d.variant_snapshot!.revision])) });
  }
  return operations;
}
