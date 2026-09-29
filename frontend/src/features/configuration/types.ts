import type { InspectionProfile } from "./knowledge/inspectionTypes";
export interface Attribute {
  key: string;
  kind: "text" | "enum" | "number" | "quantity";
  value: string | string[] | null;
  unit: string;
}
export interface EnvironmentParameter extends Attribute {
  purpose?: "product_requirement" | "project_input";
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
export interface IncludedItem {
  id: string; name: string; variant_id: string | null;
  kind: Deployment["kind"]; quantity: string | null; need_keys: string[];
  status: "draft" | "confirmed" | "disabled"; evidence: string;
}
export interface IncludedAllocation {
  id: string; demand_id: string; device_id: string; included_item_id: string;
  host_variant_id: string; host_variant_revision: number; quantity: string; evidence: string;
}
export interface IncludedOffer {
  device_id: string; included_item_id: string; host_variant_id: string; host_variant_revision: number;
  name: string; variant_id: string | null; kind: Deployment["kind"];
  status: string; reason: string; evidence: string;
  per_unit: string | null; total: string | null; allocated: string; available: string | null;
}
export interface Variant extends Authored {
  description?: string;
  supply_status?: "available" | "discontinued" | "not_for_sale";
  replacements?: string[];
  review_requirements?: Record<string, unknown>[];
  included_items?: IncludedItem[];
  capability_ids?: string[];
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
    unit?: string;
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
  schema_version?: 1 | 2;
  system_definition_id?: string;
  role_id?: string;
  activation_conditions?: Condition[];
  alternative_group?: string;
  identity_mapping?: Record<string, unknown> | null;
  quantity_review?: "unreviewed" | "confirmed";
  quantity_evidence?: string;
  resource_policy?: "unknown" | "required" | "not_applicable";
  evidence_refs?: { source_id: string; locator: string; quote: string }[];
  shared_role_refs?: { system_definition_id: string; role_id: string }[];
  scope_basis?: "listed_configurations" | "entire_scope";
  reviewed_variant_ids?: string[];
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
  quantity_unit?: string;
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
  inputs?: Attribute[];
  definition_id?: string;
  knowledge_package_id?: string;
  features?: string[];
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
  allocations?: { device_id: string; quantity: string; evidence: string }[];
  role_id?: string;
  id: string;
  system_id: string;
  role: string;
  environment: EnvironmentParameter[];
  resources: Resource[];
  device_id: string | null;
}
export interface Deployment {
  generated_origin?: { key: string; proposal_id: string; variant_locked: boolean; quantity_locked: boolean } | null;
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
  room_inputs?: Record<string, Attribute[]>;
  project_inputs?: Attribute[];
  generation?: { features_confirmed: string[]; [key: string]: unknown };
  manual_edits?: { requirements: string[]; accessory_allocations: string[]; included_allocations: string[] };
  included_allocations?: IncludedAllocation[];
  quotation?: import("./quotation/types").Quotation | null;
  calculation_version: 1 | 2 | 3;
  definition_snapshot_id?: string | null;
  accessory_choices?: { demand_id: string; selected: boolean; note?: string }[];
  supply_allocations?: SupplyAllocation[];
  rooms: Room[];
  systems: System[];
  requirements: Requirement[];
  devices: Deployment[];
  accessory_allocations: AccessoryAllocation[];
  drawing_xml: string;
  knowledge_snapshot: Knowledge[] | null;
  knowledge_snapshot_id?: string | null;
}
export interface IssueAction {
  role_id?: string; role_name?: string; feature?: string;
  system_ids?: string[];
  profile_id?: string; input_key?: string;
  rule_id?: string;
  type: string; device_id?: string; requirement_id?: string; requirement_ids?: string[]; system_id?: string; demand_id?: string; variant_id?: string; missing_fields?: string[];
}
export interface IncludedAllocationCheck extends Check {
  allocation_id: string;
  included_item_id: string;
  counted_quantity: string;
  allocated_quantity: string;
  current_host_variant_id: string | null;
  current_host_variant_revision: number | null;
  current_evidence: string;
  included_name: string;
}
export interface Check {
  check_id?: string; group_id?: string; category?: "requirements" | "selection" | "commercial" | "knowledge"; objects?: { kind: string; id: string }[];
  allocation_id?: string;
  responsibility?: "project" | "knowledge";
  code?: string;
  action?: IssueAction;
  system_id?: string;
  role_id?: string;
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
  included_allocation_checks?: IncludedAllocationCheck[];
  included_offers?: IncludedOffer[];
  included_quantity?: string;
  separately_allocated?: string;
  quantity_inputs?: { device_id: string; requirement_id?: string; source_id: string; variant_revision?: number; parameter: string; value: string | null; unit: string; error?: string | null }[];
  selected?: boolean;
  selection_conflict?: boolean;
  explanation?: Record<string, unknown>;
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
export interface ReadinessStage {
  key: "requirements" | "selection" | "accessories" | "verification" | "output";
  label: string;
  status: "pass" | "conflict" | "unknown";
  message: string;
}
export interface ProjectReadiness {
  pending_by_kind?: Record<string, number>;
  ready_for_confirmation?: boolean;
  known_checks?: Check["status"];
  coverage?: Check["status"];
  status: "pass" | "conflict" | "unknown";
  ready_for_draft: boolean;
  ready_for_confirmed_output: boolean;
  counts: {
    rooms: number;
    systems: number;
    requirements: number;
    selected_requirements: number;
    devices: number;
    conflicts: number;
    unknowns: number;
    open_accessories: number;
    accessory_unknowns?: number;
    accessory_conflicts?: number;
  };
  stages: ReadinessStage[];
}
export interface ProjectOutputConsumer {
  requirement_id: string;
  system_name: string;
  role: string;
  via: "direct" | "accessory";
}
export interface ProjectOutputLine {
  supply?: { purchase: string; existing: string; unknown: string; unassigned: string };
  device_id: string;
  kind: Deployment["kind"];
  name: string;
  model: string;
  specification: string;
  unit: string;
  quantity: string;
  note: string;
  prices: Record<string, string>;
  consumers: ProjectOutputConsumer[];
  source: {
    id: string;
    import_id: string | null;
    sheet: string | null;
    row: number | null;
  };
}
export interface ProjectOutput {
  ready_for_confirmation?: boolean;
  procurement_lines?: ProjectOutputLine[];
  status: "draft" | "confirmed";
  ready_for_confirmed_output: boolean;
  knowledge_snapshot_id: string | null;
  calculation_version: number;
  lines: ProjectOutputLine[];
}
export interface Checked {
  quotation_output?: import("./quotation/types").QuotationOutput | null;
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
  readiness: ProjectReadiness;
  project_output: ProjectOutput;
  fingerprint: string;
  versions: { id: string; revision: number }[];
  calculation_version: number;
}
export type ApplyChoice =
  | { variantId: string; sourceId: string; quantity?: string; supplySource?: SupplyAllocation["source"]; supplyEvidence?: string }
  | { existingDeviceId: string; quantity?: string };
export interface ProjectConfiguration extends Checked {
  confirmation?: { id: string; actor: string; evidence: string; project_revision: number } | null;
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

export interface SupplyAllocation {
  id: string;
  device_id: string;
  quantity: string;
  source: "purchase" | "existing" | "unknown";
  evidence: string;
}
export interface SystemDefinition extends Authored {
  id: string;
  revision: number;
  name: string;
  status: "draft" | "confirmed";
  legacy_names: string[];
  inspection_profiles?: InspectionProfile[];
  roles: { quantity_basis?: import("./knowledge/generationTypes").RoleQuantity | null; fulfilled_by?: import("./knowledge/generationTypes").RoleFulfillment | null; output_kind?: Deployment["kind"]; id: string; name: string; required: boolean; feature: string; capability_ids: string[]; inspection_profile?: { id: string; revision: number } | null }[];
}
export interface KnowledgePackage extends Authored {
  recommendations?: import("./knowledge/generationTypes").Recommendation[];
  id: string;
  revision: number;
  name: string;
  branch: string;
  status: "draft" | "published";
  system_definition_id: string;
  definition_revision: number;
  definition: SystemDefinition;
  members: { id: string; revision: number }[];
  rules: Knowledge[];
  coverage: {
    role_id: string;
    selector: Knowledge["selector"];
    accessories: "unreviewed" | "needs_review" | "complete" | "none";
    resources: "unknown" | "required" | "not_applicable";
    evidence: string;
  }[];
}
export interface Definitions {
  inspection_profiles?: InspectionProfile[];
  definitions: SystemDefinition[];
  packages: KnowledgePackage[];
  capabilities: { id: string; name: string; description: string }[];
}
export interface BusinessChange {
  kind: string;
  id: string;
  before: unknown;
  after: unknown;
}
export interface ChangePreview {
  checked: Checked;
  fingerprint: string;
  changes: BusinessChange[];
  proposed_changes: BusinessChange[];
  procurement_changes: BusinessChange[];
}
