import type { BusinessOperation, WorkbookBusinessContext } from './businessTypes';

// The server projects all earlier local edits through the same converter used by sync.
// Never derive an inverse from the fixed (potentially older) project baseline.
export function rowBusinessOperations(options: {
  configuration: WorkbookBusinessContext['configuration'];
  requirementId: string; systemId: string; deviceId?: string;
  role?: { id: string; name: string }; environmentKey: string; environmentValue: string;
  supply: string; quantity: string; evidence: string; allocationId: string;
}) {
  const { configuration, requirementId, deviceId, role } = options;
  const operations: BusinessOperation[] = [];
  const inverse: BusinessOperation[] = [];
  if (role) {
    const before = configuration.requirements.find((r) => r.id === requirementId);
    const environment = before?.environment ?? [];
    const key = options.environmentKey.trim();
    const value = { ...before, id: requirementId, system_id: options.systemId,
      role_id: role.id, role: role.name, device_id: deviceId ?? null,
      environment: key ? [...environment.filter((a) => a.key !== key),
        { key, kind: 'text', value: options.environmentValue, unit: '' }] : environment };
    operations.push({ action: 'requirement_put', value });
    inverse.push(before ? { action: 'requirement_put', value: before }
      : { action: 'remove', collection: 'requirements', id: requirementId });
  }
  if (options.supply) {
    if (!deviceId || !options.evidence.trim()) throw new Error('供货分配需要明确设备身份与依据');
    operations.push({ action: 'supply_set', device_id: deviceId, allocations: [{
      id: options.allocationId, device_id: deviceId, source: options.supply,
      quantity: options.quantity, evidence: options.evidence,
    }] });
    inverse.push({ action: 'supply_set', device_id: deviceId,
      allocations: configuration.supply_allocations.filter((a) => a.device_id === deviceId) });
  }
  return { operations, inverse };
}
