export type TemplateField =
  | 'model' | 'name' | 'description' | 'quantity' | 'unit'
  | 'brand' | 'price' | 'note' | 'section';
export type ManagedField = 'model' | 'name' | 'description' | 'unit' | 'brand' | 'price';

export interface CatalogScope { import_id: string; sheet: string }

export interface CatalogScopePreview extends CatalogScope {
  filename: string;
  matched_rows: number;
  ambiguous_rows: number;
  linked_count: number;
}

export interface TemplateProfile {
  id: string;
  revision: number;
  schema_version: number;
  name: string;
  sheet_selector: string;
  header_row: number;
  field_columns: Partial<Record<TemplateField, number>>;
  managed_fields: ManagedField[];
  normalized_header_fingerprint: string;
  created_by: string;
  catalog_scope?: CatalogScope | null;
}

export interface Candidate {
  key: string;
  group: 'direct' | 'series' | 'alternative' | 'accessory' | 'related';
  variant_id: string;
  source_id: string;
  model: string;
  name: string;
  brand: string;
  variant_name: string;
  description: string;
  unit: string;
  price: string | null;
  price_status: 'available' | 'pending';
  status: 'pass' | 'unknown' | 'conflict' | 'unassessed';
  confidence: 'high' | 'medium' | 'low';
  completion_ready: boolean;
  completion_blocker: null | 'template_source_unconfirmed' | 'source_ambiguous'
    | 'variant_ambiguous' | 'insufficient_evidence' | 'insufficient_margin';
  evidence: unknown[];
  context_reasons: string[];
  source: { import_id: string; sheet: string; row: number };
}

export interface SuggestionFeedbackPayload {
  operation_id: string;
  workbook_instance_id: string;
  template_profile_id: string;
  template_profile_revision: number;
  sheet: string;
  section: string;
  previous_variant_id?: string;
  context_previous_variant_ids: string[];
  context_next_variant_ids: string[];
  suggested_variant_id?: string;
  chosen_variant_id: string;
  chosen_source_id: string;
  query_kind: 'contextual' | 'typed';
}

export type DiagnosticEventType = 'inline_open' | 'focus_lost' | 'query_start'
  | 'query_success' | 'query_error' | 'no_match' | 'tab_register' | 'tab_restore'
  | 'tab_accept' | 'tab_expand' | 'accept_success' | 'accept_error'
  | 'completion_shown' | 'completion_accepted' | 'completion_undone'
  | 'completion_replaced' | 'completion_retained' | 'phase_timing';

export interface DiagnosticEventPayload {
  event_id: string;
  installation_id: string;
  session_id: string;
  occurred_at: string;
  plugin_version: string;
  host_os: string;
  host_version: string;
  event_type: DiagnosticEventType;
  completion_phase?: 'typing' | 'loading' | 'ghost' | 'ambiguous' | 'list' | 'no-match' | 'error'
    | 'context-build' | 'preview' | 'journal-apply';
  duration_ms?: number;
  candidate_count?: number;
  completion_ready?: boolean;
  outcome?: 'success' | 'failure' | 'expanded' | 'restored';
  error_code?: string;
  template_profile_id?: string;
  template_profile_revision?: number;
}

export type DiagnosticEventInput = Pick<DiagnosticEventPayload, 'event_type'>
  & Partial<Pick<DiagnosticEventPayload, 'event_id'>>
  & Partial<Pick<DiagnosticEventPayload,
    'completion_phase' | 'duration_ms' | 'candidate_count' | 'completion_ready'
    | 'outcome' | 'error_code' | 'template_profile_id' | 'template_profile_revision'>>;

export interface ActiveCell {
  sheet: string;
  row: number;
  column: number;
  value: string;
  formula: string;
  merged: boolean;
}

export interface InlineEditorContext {
  nonce: number;
  session_id: string;
  workbook_key?: string;
  binding_id?: string;
  profile: TemplateProfile;
  cell: ActiveCell;
  anchor: { width: number; height: number };
}

export interface LineBinding {
  line_id: string;
  sheet: string;
  row: number;
  section?: string;
  anchor_fingerprint?: string;
  content_fingerprint?: string;
  device_id?: string;
  variant_id: string;
  source_id: string;
  kind?: ProductKind;
  requirement_id?: string;
  confirmed_values?: Partial<Record<TemplateField, string>>;
}

export interface BindingState {
  binding_id: string;
  binding_revision: number;
  project_id: string | null;
  base_revision: number;
  draft_id: string;
  draft_revision: number;
  template_profile_id: string;
  template_profile_revision: number;
  managed_device_ids: string[];
  line_bindings: LineBinding[];
  created_by: string;
}

export interface WorkbookMetadata {
  schema_version: 1 | 2;
  workbook_instance_id: string;
  profile_id?: string;
  profile_revision?: number;
  binding?: BindingState;
  line_bindings: LineBinding[];
  business?: WorkbookBusinessState;
  pending_sync?: { request: Record<string, unknown>; local_revision: number;
    operations: WorkbookBusinessState['operations']; line_bindings: LineBinding[] };
}

export interface WorkbookLine {
  line_id: string;
  sheet: string;
  row: number;
  model: string;
  name: string;
  description: string;
  quantity: string;
  unit: string;
  brand: string;
  price: string | null;
  note: string;
  section: string;
  kind: 'hardware' | 'software' | 'license' | 'accessory';
  variant_id: string;
  source_id: string;
  device_id?: string;
}

export interface SheetRow {
  sheet: string;
  row: number;
  values: Partial<Record<TemplateField, string>>;
  formula_fields: TemplateField[];
  merged_fields: TemplateField[];
}

export interface ProjectSummary { id: string; name: string; revision: number }

export interface SyncPreviewResult {
  configuration?: import('./businessTypes').WorkbookBusinessContext['configuration'];
  preview_fingerprint: string;
  changes: Array<{ kind: string; id: string; before: unknown; after: unknown }>;
  issues: Array<Record<string, unknown>>;
  line_bindings: LineBinding[];
  has_changes: boolean;
  operation_count: number;
}
import type { ProductKind, WorkbookBusinessState } from './businessTypes';
