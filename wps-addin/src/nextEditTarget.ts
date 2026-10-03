import type { CompletionPreviewResult, NextEditSuggestion } from './businessTypes';
import type { HostAdapter } from './host';

// Navigation is not acceptance. After moving, request a new preview with a fresh fingerprint.
export function verifiedEditTarget(options: {
  host: Pick<HostAdapter, 'readCell' | 'readMetadata' | 'businessRevision'>;
  result: CompletionPreviewResult; suggestion: NextEditSuggestion;
}) {
  const { host, result, suggestion } = options;
  if (result.local_revision !== host.businessRevision()) throw new Error('建议已过期，请重新预览');
  const target = result.primary_suggestion_id === suggestion.id ? result.next_target : undefined;
  const patch = suggestion.patches[0];
  if (!target && !patch) throw new Error('此建议只包含业务关联，请打开差异预览');
  if (target && (target.local_revision !== result.local_revision
    || target.context_fingerprint !== result.context_fingerprint)) throw new Error('目标上下文不一致，请重新预览');
  const cell = host.readCell(target ?? patch);
  if (cell.formula || cell.merged) throw new Error('目标是公式或合并单元格，不能应用此建议');
  if (cell.value !== (target?.expected_value ?? patch.before)) throw new Error('目标原值已变化，请重新预览');
  if (target?.line_id && !host.readMetadata().line_bindings.some((line) =>
    line.line_id === target.line_id && line.sheet === target.sheet && line.row === target.row)) {
    throw new Error('产品行已移动，请重新定位并预览');
  }
  return cell;
}
