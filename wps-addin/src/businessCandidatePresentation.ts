import type { NextEditSuggestion } from './businessTypes';
import { nextEditText } from './nextEditState.ts';

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function text(value: unknown): string { return typeof value === 'string' ? value.trim() : ''; }

export function businessCandidatePresentation(suggestion: NextEditSuggestion, column: number) {
  const patch = suggestion.patches[0];
  const binding = suggestion.line_bindings.find((line) => line.sheet === patch?.sheet && line.row === patch.row)
    ?? suggestion.line_bindings[0];
  const device = record(suggestion.changes.find((change) => change.kind === 'devices'
    && binding?.device_id && record(change.after).id === binding.device_id)?.after);
  const variant = record(device.variant_snapshot);
  const source = record(device.source_snapshot);
  const title = nextEditText(suggestion, column);
  const location = patch ? `${patch.sheet} · 第 ${patch.row} 行` : '用途关联';
  if (!binding) return { title, location, configuration: suggestion.label, source: '', identity: '' };
  const configuration = [text(variant.name), text(variant.description) || text(binding.confirmed_values?.description)]
    .filter(Boolean).join(' · ') || `未提供配置说明 · 配置 ID ${binding.variant_id}`;
  const sourceRow = Number.isInteger(source.row) && Number(source.row) > 0 ? `第 ${source.row} 行` : '';
  const sourceLocation = [text(source.sheet), sourceRow, text(source.import_id) && `批次 ${source.import_id}`]
    .filter(Boolean).join(' · ');
  return { title, location, configuration, source: sourceLocation || `未提供来源位置 · 来源 ID ${binding.source_id}`,
    identity: `配置 ID ${binding.variant_id} · 来源 ID ${binding.source_id}` };
}
