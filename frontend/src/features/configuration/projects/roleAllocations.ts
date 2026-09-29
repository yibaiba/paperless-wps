import type { Requirement } from '../types';

export function requirementDeviceIds(requirement: Requirement): string[] {
  return requirement.allocations?.length
    ? requirement.allocations.map(item => item.device_id)
    : requirement.device_id ? [requirement.device_id] : [];
}

export function unlinkRoleDevice(requirement: Requirement, deviceId: string): Requirement {
  return { ...requirement,
    device_id: requirement.device_id === deviceId ? null : requirement.device_id,
    allocations: (requirement.allocations ?? []).filter(item => item.device_id !== deviceId),
  };
}
