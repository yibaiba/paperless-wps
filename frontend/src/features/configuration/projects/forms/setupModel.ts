import type { Attribute, Configuration, System } from '../../types';
export type SetupInput = { key: string; label: string; kind: Attribute['kind']; unit: string; scope: 'system' | 'role' | 'room' | 'project'; purpose: 'project_input' | 'product_requirement'; evidence: unknown[] };
export type SetupRole = { id: string; name: string; active: boolean; necessary: boolean; feature: string; inputs: SetupInput[] };
export type SetupDescription = { definition_id: string; definition_revision: number; definition_status: string; name: string; package_revision?: number; roles: SetupRole[]; features: string[]; notice: string; readiness?: { roles: { id: string; name: string; missing: string[] }[]; rules: { id: string; name: string; missing: string[] }[] } | null };
export type SetupValues = { name: string; definition_id: string; knowledge_package_id?: string; room_mode: "new" | "existing"; room_id: string; room_name: string; features?: string[]; features_confirmed?: boolean; role_ids?: string[]; inputs?: Record<string, Attribute["value"]>; actor?: string; evidence?: string };
export type SetupField = SetupInput & { roleId?: string; formKey: string };
type ScopeLocation = { systemId?: string; roomId?: string };
function scopedParameters(field: SetupField, configuration: Configuration, { systemId, roomId }: ScopeLocation) {
  const system = configuration.systems.find(s => s.id === systemId);
  if (field.scope === 'project') return configuration.project_inputs ?? [];
  if (field.scope === 'room') return configuration.room_inputs?.[roomId ?? system?.room_id ?? ''] ?? [];
  if (field.scope === 'system') return system?.inputs ?? [];
  return configuration.requirements.find(r => r.system_id === systemId && r.role_id === field.roleId)?.environment ?? [];
}
export function previousParameter(field: SetupField, configuration: Configuration, location: ScopeLocation) {
  return scopedParameters(field, configuration, location).find(v => v.key === field.key);
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
export function setupValue(field: SetupField, configuration: Configuration, location: ScopeLocation) {
  const value = scopedParameters(field, configuration, location).find(v => v.key === field.key && v.unit === field.unit)?.value ?? null;
  return field.kind === 'enum' && typeof value === 'string' ? [value] : value;
}
function fieldParameter(field: SetupField, options: { configuration: Configuration; location: ScopeLocation; inputs?: SetupValues['inputs'] }) {
  const { configuration, location, inputs } = options;
  const raw = inputs?.[field.formKey];
  const previous = previousParameter(field, configuration, location);
  if (previous && previous.unit !== field.unit && (raw === undefined || raw === null || raw === '')) throw new Error(`${field.label} 的单位已变化，请明确填写新单位下的数值；原值未改动。`);
  const value = raw === undefined ? setupValue(field, configuration, location) : raw;
  return { key: field.key, kind: field.kind, unit: field.unit, value };
}
function replaceParameter(values: Attribute[], parameter: Attribute) {
  return [...values.filter(a => a.key !== parameter.key), parameter];
}
export function setupPayload(options: { configuration: Configuration; systemId: string; roomId: string; newRoom?: { id: string; name: string }; values: SetupValues; description: SetupDescription; fields: SetupField[] }) {
  const { configuration, systemId, roomId, newRoom, values, description, fields } = options;
  const previous = configuration.systems.find(s => s.id === systemId);
  const scoped = { system: [...(previous?.inputs ?? [])], room: [...(configuration.room_inputs?.[roomId] ?? [])], project: [...(configuration.project_inputs ?? [])] };
  const environments: Record<string, Attribute[]> = {};
  for (const field of fields) {
    const parameter = fieldParameter(field, { configuration, location: { systemId, roomId }, inputs: values.inputs });
    if (field.scope !== 'role') { scoped[field.scope] = replaceParameter(scoped[field.scope], parameter); continue; }
    const existing = environments[field.roleId!] ?? configuration.requirements.find(r => r.system_id === systemId && r.role_id === field.roleId)?.environment ?? [];
    const environment = { ...parameter, purpose: field.purpose };
    environments[field.roleId!] = replaceParameter(existing, environment);
  }
  const system: System = { ...previous, id: systemId, name: values.name, room_id: roomId, kind: description.name,
    definition_id: values.definition_id, knowledge_package_id: values.knowledge_package_id ?? '', features: values.features ?? [], inputs: scoped.system };
  return { system, ...(fields.some(f => f.scope === 'room') ? { room_inputs: scoped.room } : {}), ...(fields.some(f => f.scope === 'project') ? { project_inputs: scoped.project } : {}), features_confirmed: values.features_confirmed ?? false, new_room: newRoom ?? null, role_ids: values.role_ids ?? [], role_environment: environments };
}
