import type { Attribute, Configuration, QuantityInputIssue } from '../../types';

export function scopedInputs(config: Configuration, input: QuantityInputIssue): Attribute[] {
  if (input.scope === 'project') return config.project_inputs ?? [];
  if (input.scope === 'room') {
    if (!config.rooms.some(room => room.id === input.scope_id)) throw new Error('对应房间已不存在，请重新检查');
    return config.room_inputs?.[input.scope_id] ?? [];
  }
  if (input.scope === 'system') {
    const system = config.systems.find(item => item.id === input.scope_id);
    if (!system) throw new Error('对应系统已不存在，请重新检查');
    return system.inputs ?? [];
  }
  const role = config.requirements.find(item => item.id === input.scope_id);
  if (!role) throw new Error('对应角色已不存在，请重新检查');
  return role.environment;
}

export function quantityScopeLabel(config: Configuration, input: QuantityInputIssue) {
  if (input.scope === 'project') return '整个项目';
  if (input.scope === 'room') return config.rooms.find(item => item.id === input.scope_id)?.name ?? '已移除房间';
  if (input.scope === 'system') return config.systems.find(item => item.id === input.scope_id)?.name ?? '已移除系统';
  const role = config.requirements.find(item => item.id === input.scope_id);
  const system = config.systems.find(item => item.id === role?.system_id);
  return role ? `${system?.name ?? '系统'} / ${role.role}` : '已移除角色';
}

export function applyQuantityInputs(config: Configuration, inputs: QuantityInputIssue[], values: (string | null)[]) {
  return inputs.reduce((next, input, index) => {
    const previous = scopedInputs(next, input);
    const value: Attribute = { key: input.key, kind: input.kind, unit: input.unit, value: values[index] ?? null };
    const updated = [...previous.filter(item => item.key !== input.key), value];
    if (input.scope === 'project') return { ...next, project_inputs: updated };
    if (input.scope === 'room') return { ...next, room_inputs: { ...next.room_inputs, [input.scope_id]: updated } };
    if (input.scope === 'system') return { ...next, systems: next.systems.map(item => item.id === input.scope_id ? { ...item, inputs: updated } : item) };
    return { ...next, requirements: next.requirements.map(item => item.id === input.scope_id ? { ...item, environment: updated.map(a => a.key === input.key ? { ...a, purpose: 'project_input' as const } : a) } : item) };
  }, config);
}
