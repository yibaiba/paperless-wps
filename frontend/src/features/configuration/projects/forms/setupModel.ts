import type { Attribute, Configuration, System } from '../../types';
export type SetupInput = { key: string; label: string; kind: Attribute['kind']; unit: string; scope: 'system' | 'role'; purpose: 'project_input' | 'product_requirement'; evidence: unknown[] };
export type SetupRole = { id: string; name: string; active: boolean; necessary: boolean; feature: string; inputs: SetupInput[] };
export type SetupDescription = { definition_id: string; definition_revision: number; definition_status: string; name: string; package_revision?: number; roles: SetupRole[]; features: string[]; notice: string; readiness?: { roles: { id: string; name: string; missing: string[] }[]; rules: { id: string; name: string; missing: string[] }[] } | null };
export type SetupValues = { name: string; definition_id: string; knowledge_package_id?: string; room_mode: "new" | "existing"; room_id: string; room_name: string; features?: string[]; features_confirmed?: boolean; role_ids?: string[]; inputs?: Record<string, Attribute["value"]>; actor?: string; evidence?: string };
export type SetupField = SetupInput & { roleId?: string; formKey: string };
export function previousParameter(field: SetupField, configuration: Configuration, systemId?: string) {
  const values = field.scope === 'system' ? configuration.systems.find(s => s.id === systemId)?.inputs : configuration.requirements.find(r => r.system_id === systemId && r.role_id === field.roleId)?.environment;
  return values?.find(v => v.key === field.key);
}
export function setupFields(description: SetupDescription | undefined, selected: string[]) {
  const fields = new Map<string, SetupField>();
  for (const role of description?.roles ?? []) {
    if (!selected.includes(role.id)) continue;
    for (const input of role.inputs) {
      const roleId = input.scope === 'role' ? role.id : undefined;
      const formKey = [input.scope, roleId ?? '', input.key, input.unit].join(':');
      fields.set(formKey, { ...input, roleId, formKey });
    }
  }
  return [...fields.values()];
}
export function setupValue(field: SetupField, configuration: Configuration, systemId?: string) {
  const values = field.scope === 'system' ? configuration.systems.find(s => s.id === systemId)?.inputs : configuration.requirements.find(r => r.system_id === systemId && r.role_id === field.roleId)?.environment;
  const value = values?.find(v => v.key === field.key && v.unit === field.unit)?.value ?? null;
  return field.kind === 'enum' && typeof value === 'string' ? [value] : value;
}
export function setupPayload(options: { configuration: Configuration; systemId: string; roomId: string; newRoom?: { id: string; name: string }; values: SetupValues; description: SetupDescription; fields: SetupField[] }) {
  const { configuration, systemId, roomId, newRoom, values, description, fields } = options;
  const previous = configuration.systems.find(s => s.id === systemId);
  const system: System = { ...previous, id: systemId, name: values.name, room_id: roomId, kind: description.name,
    definition_id: values.definition_id, knowledge_package_id: values.knowledge_package_id ?? '', features: values.features ?? [], inputs: [...(previous?.inputs ?? [])] };
  const environments: Record<string, Attribute[]> = {};
  for (const field of fields) {
    const original = setupValue(field, configuration, systemId);
    const raw = values.inputs?.[field.formKey];
    const existingParameter = previousParameter(field, configuration, systemId);
    if (existingParameter && existingParameter.unit !== field.unit && (raw === undefined || raw === null || raw === '')) throw new Error(`${field.label} 的单位已变化，请明确填写新单位下的数值；原值未改动。`);
    const value = raw === undefined ? original : raw;
    const parameter = { key: field.key, kind: field.kind, unit: field.unit, value, purpose: field.purpose };
    if (field.scope === 'system') system.inputs = [...(system.inputs ?? []).filter(a => a.key !== field.key), { key: field.key, kind: field.kind, unit: field.unit, value }];
    else {
      const existing = environments[field.roleId!] ?? configuration.requirements.find(r => r.system_id === systemId && r.role_id === field.roleId)?.environment ?? [];
      environments[field.roleId!] = [...existing.filter(a => a.key !== field.key), parameter];
    }
  }
  return { system, features_confirmed: values.features_confirmed ?? false, new_room: newRoom ?? null, role_ids: values.role_ids ?? [], role_environment: environments };
}
