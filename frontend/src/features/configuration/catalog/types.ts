import type { Product as Source } from "../../../shared/types";
import type { Variant } from "../types";
import type { MatchSuggestion } from "../SourceMatchSuggestions";

export interface CatalogAuditRow extends Source {
  organized: boolean;
  blocked: boolean;
  block_reason: string;
  block_actor: string;
  block_evidence: string;
  duplicate_model: boolean;
  link_revision: number;
  variant_id: string | null;
  variant: Variant | null;
  match_suggestions: MatchSuggestion[];
}

export interface CatalogAudit {
  rows: CatalogAuditRow[];
  total: number;
  organized: number;
  blocked: number;
  handled: number;
  pending: number;
  conflicts: number;
}

export type CatalogAuditStatus = "all" | "pending" | "blocked";
