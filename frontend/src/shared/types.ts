import type {AttributeProfile} from '../features/catalog/attributes/types';
export interface CatalogImport {
  id: string; filename: string; created_at: string; sheets: string[];
  record_count: number; issue_count: number; already_imported?: boolean;
}
export interface Product {
  id: string; import_id: string; model: string; name: string; brand: string;
  category: string; sheet: string; row: number; hidden: boolean; unit: string; note: string;
  attribute_profile: AttributeProfile;
  review_summary: ReviewSummary;
}
export interface ProductDetail extends Product {
  specification: string; short_specification: string; tender_specification: string;
  prices: Record<string, string>; sources: Record<string, string>;
  issues: Issue[];
}
export type ReviewStatus = 'pending' | 'confirmed_variant' | 'equivalent' | 'source_error';
export interface ReviewSummary { total: number; pending: number; source_error: number }
export interface ReviewDecision {
  revision: number; status: ReviewStatus;
  id?: string; actor?: string; note?: string; created_at?: string;
}
export interface Issue {
  id: string; import_id: string; kind: string; title: string; description: string;
  evidence: { sheet: string; range: string; model: string; value: string }[];
  review: ReviewDecision; history: ReviewDecision[];
}
export interface Project {
  id: string; name: string; created_at: string; item_count: number;
}
export interface ProjectItem {
  id: string; product_id: string; quantity: string; group_name: string;
  note: string; snapshot: Omit<ProductDetail, 'issues' | 'review_summary' | 'id'>;
  review_summary: ReviewSummary;
}
export interface ProjectDetail { id: string; name: string; items: ProjectItem[] }
