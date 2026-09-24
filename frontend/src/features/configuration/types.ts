export interface Attribute {
  key: string;
  kind: "text" | "enum" | "number" | "quantity";
  value: string | string[] | null;
  unit: string;
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
  target_variant_ids: string[];
  accessory_type: "required" | "recommended" | "optional";
  mode: "per_unit" | "per_capacity" | "per_group";
  factor: string;
  shared_roles: string[];
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
  kind: "hardware" | "software" | "accessory";
  note: string;
  variant_snapshot: Variant | null;
  source_snapshot: Record<string, unknown> | null;
  origin_suggestion: string | null;
}
export interface Configuration extends Authored {
  rooms: Room[];
  systems: System[];
  requirements: Requirement[];
  devices: Deployment[];
  drawing_xml: string;
  knowledge_snapshot: Knowledge[] | null;
  knowledge_snapshot_id?: string | null;
}
export interface Check {
  kind: string;
  status: "pass" | "conflict" | "unknown";
  device_id?: string;
  requirement_id?: string;
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
  required?: string;
  missing?: string;
  existing?: string;
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
  fingerprint: string;
  versions: { id: string; revision: number }[];
}
export interface ProjectConfiguration extends Checked {
  id?: string;
  name: string;
  revision: number;
  project_id: string;
  legacy_items?: number;
}
export interface Candidate {
  variant: Variant;
  status: "pass" | "conflict" | "unknown";
  evidence: Record<string, unknown>[];
}
