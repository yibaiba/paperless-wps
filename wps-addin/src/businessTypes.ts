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
}
export interface CompletionPreviewResult {
  items: NextEditSuggestion[]; issues: unknown[]; context_fingerprint: string;
  local_revision: number; versions: Record<string, string | null>; line_bindings: LineBinding[];
  configuration: WorkbookBusinessContext['configuration'];
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
  recovery?: { intent: 'undo' | 'rollback'; before: WorkbookMetadata; after: WorkbookMetadata };
}
