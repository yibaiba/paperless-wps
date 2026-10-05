import type { LineBinding, TemplateField, WorkbookLine, WorkbookMetadata } from './types';

export type ProductKind = 'hardware' | 'software' | 'license' | 'accessory';
export type BusinessOperation = Record<string, unknown> & { action: string };
export interface BusinessScope {
  sheet: string; start_row: number; end_row: number;
  room_id: string | null; system_id: string; requirement_id?: string | null;
}
export interface RecentBusinessEdit {
  operation_id: string; kind: 'accept' | 'replace' | 'quantity' | 'remove' | 'undo' | 'dismiss';
  suggestion_id?: string; device_id?: string; requirement_id?: string;
  line_id?: string; sheet?: string; row?: number; sequence?: number;
  semantic_action_id?: string; business_context_fingerprint?: string;
  changes?: NextEditSuggestion['changes'];
}
export interface WorkbookBusinessState {
  local_revision: number;
  scopes: BusinessScope[];
  operations: BusinessOperation[];
  recent_edits: RecentBusinessEdit[];
  row_requirements?: Array<{ sheet: string; row: number; requirement_id: string }>;
  removed_lines?: WorkbookLine[];
  unresolved_line_ids?: string[];
}
export interface BusinessAttribute { key: string; kind: string; value: string; unit: string }
export interface BusinessSystem {
  id: string; name: string; kind: string; room_id: string | null;
  definition_id: string; knowledge_package_id: string; inputs: BusinessAttribute[];
  features: string[];
}
export interface BusinessRequirement {
  id: string; system_id: string; role_id: string; role: string; device_id: string | null;
  allocations: Array<{ device_id: string; quantity: string; evidence: string }>;
  environment?: BusinessAttribute[];
}
export interface BusinessDevice {
  id: string; name: string; kind: ProductKind; variant_id: string; source_id: string;
  quantity: string; note: string;
}
export interface WorkbookBusinessContext {
  binding_revision: number; draft_revision: number; project_revision: number;
  versions: Record<string, string | null>; fingerprint: string;
  knowledge_summary?: KnowledgeSummary[];
  configuration: {
    rooms: Array<{ id: string; name: string }>;
    systems: BusinessSystem[]; requirements: BusinessRequirement[]; devices: BusinessDevice[];
    supply_allocations: Array<Record<string, unknown>>;
    generation: Record<string, unknown>;
    room_inputs?: Record<string, BusinessAttribute[]>;
    project_inputs?: BusinessAttribute[];
  };
  definitions: {
    packages: Array<{ id: string; name: string; system_definition_id: string;
      definition: { roles: Array<{ id: string; name: string; output_kind: ProductKind;
        feature: string; quantity_basis?: { scope: string; input_key: string; input_unit: string; mode: string } | null }> } }>;
  };
}
export interface CellPatch {
  sheet: string; row: number; column: number; field: TemplateField;
  before: string; after: string;
}
export interface NextEditSuggestion {
  id: string; kind: string; label: string; patches: CellPatch[];
  line_bindings: LineBinding[]; business_operations: BusinessOperation[];
  inverse_business_operations?: BusinessOperation[];
  row_requirements?: WorkbookBusinessState['row_requirements'];
  removed_lines?: WorkbookLine[];
  confirmed_identity_ids?: string[];
  changes: Array<{ kind: string; id: string; before: unknown; after: unknown }>;
  evidence: unknown[]; issues: unknown[]; applicable: boolean;
  acceptance: 'inline' | 'preview'; context_fingerprint: string; local_revision: number;
  semantic_action_id?: string; business_context_fingerprint?: string;
}
export interface NextEditTarget {
  sheet: string; row: number; column: number; field: TemplateField;
  line_id: string | null; expected_value: string;
  local_revision: number; context_fingerprint: string;
}
export interface EditDecision {
  status: 'ready' | 'choice_required' | 'confirmation_required' | 'satisfied' | 'no_match' | 'dismissed';
  reason_code: string;
}
export interface CompletionPreviewResult {
  items: NextEditSuggestion[]; issues: unknown[]; context_fingerprint: string;
  local_revision: number; versions: Record<string, string | null>; line_bindings: LineBinding[];
  configuration: WorkbookBusinessContext['configuration'];
  primary_suggestion_id?: string | null;
  decision?: EditDecision;
  next_target?: NextEditTarget | null;
  context_summary?: CompletionContextSummary;
}
export interface UnresolvedWorkbookRow {
  sheet: string; row: number; line_id?: string; device_id?: string;
  system_id?: string | null; reason_code: string;
  confirmed_line?: WorkbookLine;
}
export interface ResolutionAction {
  kind: 'locate_row' | 'confirm_identity' | 'check_source' | 'edit_business' | 'review_knowledge';
  label: string; sheet: string; row: number; column: number;
  requirement_id?: string | null; device_id?: string | null;
  expected_local_revision: number; context_fingerprint: string;
  binding_id: string; template_profile_revision: number;
}
export interface KnowledgeSummary {
  system_id: string; system_name: string;
  definition: { id: string; revision: number; name: string; status: string } | null;
  package: { id: string; revision: number; name: string; status: string } | null;
  gaps: unknown[];
}
export interface CompletionContextSummary {
  mode: 'business'; project_id: string; scope: BusinessScope;
  system: { id: string; name: string; kind: string };
  room: { id: string; name: string } | null;
  versions: Record<string, string | null>; local_revision: number;
  catalog_scope: { import_id: string; sheet: string };
  input_resolution?: {
    status: 'matched' | 'no_catalog_match' | 'outside_source' | 'selection_mismatch';
    catalog_match_count: number; scoped_match_count: number; selected_match_count: number;
    variant_ids: string[];
  } | null;
  rows: Array<Pick<BusinessDevice, 'id' | 'name' | 'kind' | 'quantity' | 'variant_id' | 'source_id'> & {
    line_id: string | null; sheet: string | null; row: number | null;
    participation: 'dependency' | 'inventory' | 'business_area';
    supply_allocations: Array<{ source: string; quantity: string }>;
    uses: Array<{ requirement_id: string; system_id: string; role: string }>;
  }>;
  unresolved_rows?: UnresolvedWorkbookRow[];
  local_changes: Array<{ kind: string; id: string }>;
  knowledge: KnowledgeSummary[]; issues: unknown[];
}
export interface WorkbookEditJournal {
  operation_id: string; suggestion_id: string; created_at: string;
  state: 'prepared' | 'applied' | 'undone' | 'restored' | 'recovery_required';
  patches: CellPatch[];
  before: Pick<WorkbookMetadata, 'line_bindings' | 'business'>;
  after: Pick<WorkbookMetadata, 'line_bindings' | 'business'>;
  error?: string;
  binding_revision?: number;
  binding_id?: string;
  inverse_business_operations?: BusinessOperation[];
  semantic_action_id?: string; business_context_fingerprint?: string;
  recovery?: { intent: 'undo' | 'rollback'; before: WorkbookMetadata; after: WorkbookMetadata };
}
