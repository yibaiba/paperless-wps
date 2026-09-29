import type { Authored, Knowledge } from '../types';

export interface RoleQuantity extends Authored {
  status: 'draft' | 'confirmed'; scope: 'system' | 'room' | 'project';
  input_key: string; input_unit: string; mode: 'per_unit' | 'per_capacity' | 'per_group' | null;
  factor: string | null; evidence_refs: NonNullable<Knowledge["evidence_refs"]>;
}
export interface RoleFulfillment extends Authored {
  status: 'draft' | 'confirmed'; role_id: string; need_key: string; evidence_refs: NonNullable<Knowledge["evidence_refs"]>;
}
export interface Recommendation extends Authored {
  role_id: string; need_key: string; status: 'draft' | 'confirmed';
  variant_ids: string[]; conditions: Knowledge['conditions']; evidence_refs: NonNullable<Knowledge["evidence_refs"]>;
}
