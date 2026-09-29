import type { Knowledge, Variant } from '../types';

// A partial selector from Form must not discard category, exclusions or series.
export function mergeQuickEdit(original: Partial<Knowledge>, values: Partial<Knowledge>) {
  return { ...original, ...values, selector: { ...original.selector, ...values.selector } } as Knowledge;
}
export function requiresAdvanced(value: Partial<Knowledge>) {
  return !!(value.activation_conditions?.length || value.alternative_group || value.selector?.category ||
    value.selector?.series.length || value.selector?.exclude_variant_ids.length);
}
export function matchingConfigurations(value: Partial<Knowledge>, variants: Variant[]) {
  const s = value.selector;
  if (!s) return [];
  return variants.filter(v => !s.exclude_variant_ids?.includes(v.id) &&
    (!s.variant_ids?.length || s.variant_ids.includes(v.id)) &&
    (!s.category || s.category === v.product.category) &&
    (!s.series?.length || s.series.some(series => v.series.includes(series))));
}
export function copyKnowledge(value: Knowledge) {
  const { id: _id, revision: _revision, ...fields } = value;
  return { ...fields, schema_version: 2, status: 'draft', quantity_review: 'unreviewed', name: value.name + '（草稿副本）' } as Knowledge;
}
