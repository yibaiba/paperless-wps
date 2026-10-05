import type { DeviceConsumer, Resource } from '../types';

export interface QuantitySummary {
  total_quantity: string; independent_quantity: string; shared_quantity: string;
  reserved_quantity: string; unassigned_quantity: string; overallocated_quantity: string;
}
export interface RoleReference {
  requirement_id: string; quantity: string; group_ids: string[];
  demand_ids: string[]; fulfilled_by_requirement_ids: string[]; resources: Resource[];
}
export interface UsageGroup {
  id: string; device_id: string; mode: string; quantity: string;
  requirement_ids: string[]; demand_ids: string[]; allocation_ids: string[];
  consumers: DeviceConsumer[]; role_references: RoleReference[];
}
export interface UsageProjectionStatus {
  version?: number; fingerprint?: string; current?: boolean; required_version?: number; message?: string;
}
export interface UsageState {
  quantity_summary?: QuantitySummary;
  groups: Pick<UsageGroup, 'id' | 'mode' | 'quantity' | 'requirement_ids' | 'demand_ids'>[];
}
