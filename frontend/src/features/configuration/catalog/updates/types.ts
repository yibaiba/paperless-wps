import type { Variant } from '../../types';
export const updateRoot = '/catalog-updates';
export const priceColumns = ['出厂指导价', '甲方指导价', '总包指导价', '项目参考价格', '市场参考报价', '最低客户报价'];
export const classifications: Record<string, string> = { unchanged: '无变化', prices: '仅价格变化', information: '资料变化', specification: '规格变化', new: '新产品', unmatched: '匹配待确认', manual: '人工维护' };
export const actions = [
  { value: 'prices', label: '确认归属 / 只更新价格' }, { value: 'display', label: '修正名称或展示文字' },
  { value: 'new_variant', label: '规格变化：建立独立配置' }, { value: 'correct', label: '原资料错误：修正原配置' },
  { value: 'new_product', label: '建立新产品及配置' }, { value: 'supply', label: '修改供货状态 / 替代候选' }, { value: 'defer', label: '保留待核对' },
];
export interface PriceChange { column: string; state: 'keep' | 'skip' | 'amount' | 'inquiry'; amount?: string | null; effective_date: string }
export interface Decision { action: string; variant_id: string; expected_variant_revision: number; actor: string; evidence: string; prices: PriceChange[]; variant?: object; product?: { model: string; name: string; actor: string; evidence: string }; supply_status?: string; replacements?: string[]; copy_rule_ids?: string[]; manual_unit?: string; manual_specification?: string }
export interface Source { id: string; model: string; name: string; sheet: string; row: number; specification: string; note: string; prices: Record<string, string>; sources: Record<string, unknown> }
export interface Candidate { classification: string; variant_id: string; name: string; baseline: Source; baseline_conflict: boolean; baselines: { source: Source; differences: string[] }[]; differences: { field: string; before: unknown; after: unknown }[] }
export interface UpdateRow { pending_prices?: string[]; id: string; source: Source | null; variant_id: string; classification: string; state: string; candidates: Candidate[]; decision: Decision | null }
export interface Batch { id: string; name: string; revision: number; actor: string; evidence: string; rows: UpdateRow[]; total: number; counts?: Record<string, number> }
export interface Preview { fingerprint: string; changes: { row_id: string; pending_prices?: string[]; decision: Decision; impact?: { rules: { name: string }[]; packages: { name: string }[]; projects: { project_id: string }[] }; prices: { before: { amount: string; state: string } | null; after: PriceChange }[] }[] }
export function beijingDate() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); }
export function variantPayload(value: Variant | undefined) {
  if (!value) return { product_id: 'new', name: '', status: 'confirmed', attributes: [], series: [], functions: [], interfaces: [], systems: [] };
  const { product_id, name, status, attributes, series, functions, interfaces, systems, included_items, capability_ids, description, supply_status, replacements, review_requirements } = value;
  return { product_id, name, status, attributes, series, functions, interfaces, systems, included_items, capability_ids, description, supply_status, replacements, review_requirements };
}

export function priceDefaults(prices: PriceChange[] = [], day = beijingDate()) {
  return priceColumns.map(column => prices.find(p => p.column === column) ?? { column, state: 'skip' as const, amount: null, effective_date: day });
}

export function defaultAction(classification: string) { return classification === "specification" ? "new_variant" : classification === "new" ? "new_product" : "prices"; }

export function priceDecisions(values: Omit<PriceChange, 'column'>[]) {
  return values.map((p, index) => ({ ...p, column: priceColumns[index], amount: p.state === 'amount' ? p.amount : null }));
}
