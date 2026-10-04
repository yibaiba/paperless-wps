import type { EvidenceReference, ProjectOutputLine } from '../types';
export type CaseBinding = { row_id: string; device_ids: string[]; requirement_ids: string[]; demand_ids: string[]; included_allocation_ids: string[];
  disposition: 'compare' | 'not_enabled' | 'unresolved'; feature_system_id: string; feature: string; evidence: string };
export type CaseReference = { id: string; revision: number; bindings: CaseBinding[] };
export type CaseRow = { row_id: string; original: { section: string; name: string; model: string; quantity: string | null; unit: string; questions: string[]; evidence_refs: EvidenceReference[]; raw: Record<string, string> };
  binding?: CaseBinding; status: string; reason: string; device_ids: string[]; current: ProjectOutputLine[]; deployed: string; purchase: string; existing: string; included: string; quantity_delta: string | null; mapped_quantity: string | null; evidence?: string; issues: { message?: string; code?: string; status: string }[] };
export type Comparison = { case: { id: string; revision: number; name: string } | null; rows: CaseRow[]; additional: ProjectOutputLine[]; notice: string };
