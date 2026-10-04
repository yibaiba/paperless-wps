import type { EditDecision } from './businessTypes';

export function completionMode(version: number) {
  return version === 2 ? '业务上下文推荐' : '基础产品补全';
}

export function decisionText(decision?: EditDecision) {
  if (!decision) return '当前服务未提供决策说明';
  const reasons: Record<string, string> = {
    exact_input: '优先匹配你明确输入的产品', existing_reuse: '已有设备可满足需求，优先复用',
    unique_candidate: '当前条件下只有一个有效方案', confirmed_order: '按已确认的业务推荐顺序选择',
    source_ambiguous: '同一产品存在多个来源，请明确选择',
    variant_ambiguous: '同型号存在多个配置，请明确选择', alternatives: '有多个可行方案，请明确选择',
    evidence_required: '业务依据或参数尚未确认', identity_ambiguous: '产品身份或用途尚未确认',
    typed_no_match: '工作簿固定目录中没有匹配产品，请核对输入和目录版本',
    typed_no_edit: '当前输入未产生新的业务修改',
    typed_source_excluded: '目录有匹配产品，但不在模板确认的来源范围',
    typed_role_unresolved: '目录有匹配产品，但缺少当前用途的适用依据',
    typed_selection_stale: '已选配置或来源与当前输入不一致，请重新选择',
    requirements_satisfied: '当前受检范围的需求已满足，停止推荐', suggestion_dismissed: '已撤销或拒绝的动作不再重复推荐',
  };
  return reasons[decision.reason_code] ?? `决策：${decision.status}（${decision.reason_code}）`;
}

export function issueText(issue: unknown): string {
  if (typeof issue === 'string') return issue;
  if (!issue || typeof issue !== 'object') return JSON.stringify(issue) ?? String(issue);
  const value = issue as Record<string, unknown>;
  if (!('message' in value)) return JSON.stringify(value);
  const origins: Record<string, string> = {
    catalog_data: '目录数据', catalog_scope: '来源范围', knowledge: '知识依据', business_context: '业务上下文',
  };
  const location = [value.sheet, value.row ? `第 ${value.row} 行` : '',
    value.field ? `字段 ${value.field}` : '', value.requirement_id ? `用途 ${value.requirement_id}` : '']
    .filter(Boolean).join(' · ');
  return [origins[String(value.origin)], location, String(value.message)].filter(Boolean).join('：');
}
