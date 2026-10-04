import type { Configuration, IssueAction, Suggestion } from '../types';

export function accessoryOpenItems(item: Suggestion, configuration: Configuration) {
  if (item.selected === false || (item.status === 'pass' && Number(item.missing ?? 0) === 0)) return [];
  const common = {
    object: item.need_name || item.rule.name,
    status: item.status === 'conflict' ? 'conflict' as const : 'unknown' as const,
    href: '/knowledge?' + new URLSearchParams({ rule: item.rule.id }),
  };
  const rows: (typeof common & { id: string; category: string; action: IssueAction; message: string })[] = [];
  if (item.input_issues?.length) rows.push({
    ...common, id: `input:${item.id}`, category: '需求',
    message: [...new Set(item.input_issues.map(i => `${i.label}：${i.message}`))].join('；'),
    action: { type: 'edit_quantity_inputs', demand_id: item.id, rule_id: item.rule.id,
      missing_fields: [...new Set(item.input_issues.map(i => i.key))], quantity_inputs: item.input_issues },
  });
  if (!item.input_issues_only) rows.push({
    ...common, id: `suggestion:${item.id}`,
    category: item.missing_information?.length ? '公共知识' : '选型配套',
    action: { type: item.missing_information?.length ? 'edit_knowledge' : 'edit_accessory', demand_id: item.id, rule_id: item.rule.id, variant_id: configuration.devices.find(d => d.id === item.scope_id)?.variant_id },
    message: item.status === 'pass' ? `需要 ${item.required}，已分配 ${item.existing}，还缺 ${item.missing}` : item.missing_information?.join('；') || '配套条件尚未确认',
  });
  return rows;
}
