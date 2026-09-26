export interface Attribute {
  key: string;
  kind: "text" | "enum" | "number" | "quantity";
  value: string | string[] | null;
  unit: string;
}
export interface AttributeDefinition {
  key: string;
  label: string;
  kind: Attribute["kind"];
  units: string[];
  aliases: string[];
}
export interface Authored {
  actor: string;
  evidence: string;
}
export interface Product extends Authored {
  id: string;
  revision: number;
  name: string;
  model: string;
  brand: string;
  category: string;
}
export interface Variant extends Authored {
  id: string;
  revision: number;
  product_id: string;
  name: string;
  status: "draft" | "confirmed";
  attributes: Attribute[];
  series: string[];
  functions: string[];
  interfaces: string[];
  systems: string[];
  source_ids: string[];
  source_details?: {
    id: string;
    sheet: string;
    row: number;
    import_id: string;
    specification?: string;
    note?: string;
  }[];
  source_differences?: string[];
  product: Product;
}
export interface Condition {
  field: string;
  operator: "eq" | "any" | "all" | "range";
  value: string | string[] | null;
  minimum: string | null;
  maximum: string | null;
  unit: string;
}
export interface Knowledge extends Authored {
  id: string;
  revision: number;
  name: string;
  kind: "suitability" | "accessory" | "sharing";
  status: "draft" | "confirmed" | "disabled";
  effect: "allow" | "deny";
  selector: {
    variant_ids: string[];
    category: string;
    series: string[];
    exclude_variant_ids: string[];
  };
  system: string;
  role: string;
  conditions: Condition[];
  need_key: string;
  need_name: string;
  target_variant_ids: string[];
  accessory_type: "required" | "recommended" | "optional";
  calculation_scope: "device" | "system" | "room" | "project" | null;
  quantity_source: "device_quantity" | "environment";
  quantity_key: string;
  mode: "per_unit" | "per_capacity" | "per_group" | null;
  factor: string | null;
  output_kind: "hardware" | "software" | "license" | "accessory";
  allocation_mode: "consumable" | "shareable";
  shared_roles: string[];
  completion?: "complete" | "incomplete";
  missing_fields?: string[];
  migration_source?: {
    legacy_rule_id: string;
    legacy_rule_revision: number;
  } | null;
}
export interface Room {
  id: string;
  name: string;
}
export interface System {
  id: string;
  room_id: string | null;
  name: string;
  kind: string;
}
export interface Resource {
  key: string;
  amount: string;
  unit: string;
  applies_to?: "selected_device" | "accessory";
  target_need_key?: string;
}
export interface Requirement {
  id: string;
  system_id: string;
  role: string;
  environment: Attribute[];
  resources: Resource[];
  device_id: string | null;
}
export interface Deployment {
  id: string;
  name: string;
  variant_id: string;
  source_id: string;
  quantity: string;
  kind: "hardware" | "software" | "license" | "accessory";
  note: string;
  variant_snapshot: Variant | null;
  source_snapshot: Record<string, unknown> | null;
  origin_suggestion: string | null;
}
export interface AccessoryAllocation {
  id: string;
  demand_id: string;
  device_id: string;
  quantity: string;
  evidence: string;
}
export interface Configuration extends Authored {
  calculation_version: 1 | 2;
  rooms: Room[];
  systems: System[];
  requirements: Requirement[];
  devices: Deployment[];
  accessory_allocations: AccessoryAllocation[];
  drawing_xml: string;
  knowledge_snapshot: Knowledge[] | null;
  knowledge_snapshot_id?: string | null;
}
export interface Check {
  kind: string;
  status: "pass" | "conflict" | "unknown";
  device_id?: string;
  requirement_id?: string;
  demand_id?: string;
  message?: string;
  resource?: string;
  unit?: string;
  required?: string;
  capacity?: string;
  evidence?: Record<string, unknown>[];
}
export interface Suggestion {
  id: string;
  parent_id: string;
  rule: Knowledge;
  status: string;
  scope?: "device" | "system" | "room" | "project" | null;
  scope_id?: string;
  need_key?: string;
  need_name?: string;
  consumer_requirement_ids: string[];
  required?: string | null;
  missing?: string | null;
  existing?: string;
  surplus?: string;
  missing_information?: string[];
  calculation?: {
    engine: string;
    expression: string;
    input: Record<string, string>;
  } | null;
}
export interface DeviceConsumer {
  requirement_id: string;
  system_id: string;
  system_name: string;
  system: string;
  role: string;
  via: "direct" | "accessory";
  demand_id: string | null;
  resources: Resource[];
  capacity_expected: boolean;
}
export interface DeviceUsage {
  device_id: string;
  consumers: DeviceConsumer[];
  allocation_demand_ids: string[];
  missing_information: string[];
}
export interface Checked {
  version_changes?: {
    kind: string;
    id: string;
    used: number | null;
    current: number;
  }[];
  configuration: Configuration;
  checks: Check[];
  suggestions: Suggestion[];
  device_usages: DeviceUsage[];
  fingerprint: string;
  versions: { id: string; revision: number }[];
  calculation_version: number;
}
export type ApplyChoice =
  | { variantId: string; sourceId: string; quantity?: string }
  | { existingDeviceId: string; quantity?: string };
export interface ProjectConfiguration extends Checked {
  id?: string;
  name: string;
  revision: number;
  project_id: string;
  legacy_items?: number;
}
export type CandidateMode = "known" | "semantic" | "all";
export interface Candidate {
  variant: Variant;
  status: "pass" | "conflict" | "unknown";
  evidence: Record<string, unknown>[];
  ranking: {
    rank: number;
    score: number;
    embedding_model: string;
    reranker_model: string;
    document_revision: number;
  } | null;
}
