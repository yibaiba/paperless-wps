import type { Check, Configuration, DeviceUsage } from '../types';

export const usageModes: Record<string, string> = {
  direct: '角色独立分配', consumable: '耗用配套', shareable: '单用途可共享设备',
  shared: '共用实例', unresolved: '待重新关联的配套',
};

export function usageDetails(usage: DeviceUsage, configuration: Configuration) {
  const requirements = new Map(configuration.requirements.map(r => [r.id, r]));
  const systems = new Map(configuration.systems.map(s => [s.id, s]));
  const rooms = new Map(configuration.rooms.map(r => [r.id, r]));
  return (usage.allocation_groups ?? []).map(group => ({
    ...group,
    label: usageModes[group.mode] ?? group.mode,
    consumers: group.requirement_ids.map(id => {
      const requirement = requirements.get(id);
      const system = requirement && systems.get(requirement.system_id);
      const room = system?.room_id ? rooms.get(system.room_id) : undefined;
      return { id, label: [room?.name, system?.name, requirement?.role ?? `待核对角色：${id}`].filter(Boolean).join(' / ') };
    }),
  }));
}

export function deviceChecks(checks: Check[], deviceId: string) {
  return checks.filter(check => check.device_id === deviceId || check.device_ids?.includes(deviceId));
}
