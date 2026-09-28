import { applyProjectionPatch, type ProjectionPatch } from "./projectionPatch";
import { api } from '../../../../shared/api';
import type { Checked, Configuration, Deployment } from '../../types';
import type { Operation } from './operations';

export interface Workspace {
  id: string; revision: number; project_id: string; base_revision: number; name: string;
  configuration: Configuration; checked: Checked; updated_at: string;
}
export interface Delta {
  id: string; revision: number; checked_patch: ProjectionPatch | null;
  configuration_patch: Partial<Configuration> & { device_changes?: (Partial<Deployment> & { id: string })[]; device_order?: string[] };
}
export const post = <T,>(path: string, value: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(value) });
export function mergeDelta(workspace: Workspace, delta: Delta): Workspace {
  const { device_changes, device_order, ...patch } = delta.configuration_patch;
  const devices = new Map(workspace.configuration.devices.map((device) => [device.id, device]));
  for (const change of device_changes ?? []) devices.set(change.id, { ...devices.get(change.id), ...change } as Deployment);
  const configuration = { ...workspace.configuration, ...patch,
    devices: device_order ? device_order.map((id) => devices.get(id)!) : device_changes ? workspace.configuration.devices.map((d) => devices.get(d.id)!) : workspace.configuration.devices };
  return { ...workspace, revision: delta.revision, configuration, checked: { ...applyProjectionPatch(workspace.checked, delta.checked_patch) as Checked, configuration } };
}
export function writeRequest(workspace: Workspace, operations: Operation[]) {
  return { draft_id: workspace.id, expected_revision: workspace.revision, operation_id: crypto.randomUUID(), operations };
}
