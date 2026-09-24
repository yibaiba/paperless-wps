import type {SourceSelector,AttributeProfile} from '../catalog/attributes/types';
import type {Issue} from '../../shared/types';
export interface RuleProduct {
  id: string; import_id: string; model: string; name: string; sheet: string; row: number; unit: string;
}
export interface AccessoryRule {
  matching_errors?:string[]; id: string; revision: number; name: string; source_product_id: string | null; source_selector: SourceSelector | null; attribute_snapshot?:Record<string,AttributeProfile>; target_product_id: string;
  source: RuleProduct | null; target: RuleProduct; sources: RuleProduct[]; targets: RuleProduct[];
  additional_source_ids: string[]; alternative_target_ids: string[]; relation: 'quantity' | 'required' | 'choice';
  mode: 'per_capacity' | 'per_unit' | 'per_group'; factor: string;
  status: 'draft' | 'active' | 'disabled'; evidence: string; actor: string; updated_at: string;
}
export interface Calculation {
  quantity: string; engine: string; expression: string; input: {quantity: string; factor: string};
}
export interface RuleMatch extends Calculation {
  sources?: RuleProduct[]; contributions?: {product_id:string;quantity:string}[];
  rule_id: string; revision: number; name: string; evidence: string; source: RuleProduct | null; source_selector?:SourceSelector|null; attribute_snapshot?:Record<string,AttributeProfile>;
}
export interface Suggestion {
  id: string; group_name: string; target: RuleProduct; required: string; existing: string;
  missing: string; surplus: string; mandatory: boolean; rules: RuleMatch[];
}
export interface RulePreview {
  project_id: string; fingerprint: string; engine: string; active_rule_count: number;
  suggestions: Suggestion[];
  choice_checks?: ChoiceCheck[]; pending_relations?: AccessoryRule[]; source_concerns?: Issue[];
  uncovered_items: {id: string; model: string; group_name: string; quantity: string}[];
}
export interface ChoiceCheck {
  id:string; group_name:string; rule:RuleMatch; targets:RuleProduct[];
  required:string; existing:string; missing:string; status:'needs_selection'|'quantity_satisfied';
}
export interface RuleApplication {
  id: string; created_at: string; item_ids: string[]; calculation: RulePreview;
}
export const statusLabels = {draft: '草稿', active: '启用', disabled: '停用'};
export const relationLabels = {quantity:'数量配套', required:'必须配套', choice:'必须配套，人工选择候选'};
export const modeLabels = {per_group: '每个系统的最低数量',per_capacity: '按承载量，向上取整', per_unit: '按用量，直接相乘'};
export const productLabel = (p: RuleProduct) => `${p.model} · ${p.name} · ${p.sheet} 第${p.row}行`;
