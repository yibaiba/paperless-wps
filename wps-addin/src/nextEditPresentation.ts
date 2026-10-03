import type { NextEditSuggestion } from './businessTypes';
import type { ActiveCell } from './types';
import { nextEditText, visiblePrefix } from './nextEditState.ts';

export const NEXT_EDIT_NOTICE_ROWS = 3;

const FIELD_NAMES: Record<string, string> = {
  model: '型号', name: '名称', description: '说明', quantity: '数量', unit: '单位',
  price: '单价', brand: '品牌', note: '备注', section: '分区',
};

function evidenceText(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim()) return value;
  if (Array.isArray(value)) return value.map(evidenceText).find(Boolean);
  if (!value || typeof value !== 'object') return undefined;
  const record = value as Record<string, unknown>;
  for (const key of ['reason', 'message', 'explanation', 'evidence', 'calculation',
    'expression', 'basis', 'compatibility', 'recommendation', 'rule', 'name']) {
    const result = evidenceText(record[key]);
    if (result) return result;
  }
  return undefined;
}

export function nextEditNotice(options: {
  suggestion?: NextEditSuggestion; cell: ActiveCell; query: string;
}) {
  const { suggestion, cell, query } = options;
  if (!suggestion) return undefined;
  const target = suggestion.patches[0];
  const elsewhere = target && (target.sheet !== cell.sheet || target.row !== cell.row);
  const prefix = visiblePrefix(suggestion, cell.column, query);
  if (!elsewhere && prefix) return undefined;
  const location = target ? `${target.sheet} · 第 ${target.row} 行 · ${FIELD_NAMES[target.field] ?? target.field}` : '业务关联';
  return {
    target: `${location}：${nextEditText(suggestion, cell.column)}`,
    reason: evidenceText(suggestion.evidence) ?? '未提供文字理由，请展开核对结构化证据',
    action: !prefix ? 'Tab 展开候选，明确选择后接受' : 'Tab 仅定位，不写入；定位后再次确认',
  };
}
