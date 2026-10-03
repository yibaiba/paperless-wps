import type { NextEditSuggestion, RecentBusinessEdit, WorkbookEditJournal } from './businessTypes';
import type { WorkbookMetadata } from './types';
import type { WorkbookRowIndex } from './workbookRowIndex';
import { bindingForRow } from './workbook.ts';

export function observedQuantityEdits(index: WorkbookRowIndex, metadata: WorkbookMetadata): RecentBusinessEdit[] {
  const sequence = nextEditSequence(metadata.business?.recent_edits ?? []);
  return index.recentChanges().flatMap(({ before, after, order, historyKey }, offset) => {
    if (historyKey !== recentHistoryKey(metadata)) return [];
    const binding = bindingForRow(after, metadata.line_bindings);
    if (!binding?.device_id || !binding.confirmed_values) return [];
    const quantity = after.values.quantity;
    // Only host-committed quantities with a confirmed identity are business events.
    // Plugin writes already appear in the journal; model/name keystrokes stay queries.
    if (quantity === before.values.quantity || quantity === binding.confirmed_values.quantity) return [];
    return [{ operation_id: `row:${binding.line_id}:${order}`, kind: 'quantity' as const,
      line_id: binding.line_id, device_id: binding.device_id, requirement_id: binding.requirement_id,
      sheet: after.sheet, row: after.row, sequence: sequence + offset,
      changes: [{ kind: 'devices', id: binding.device_id,
        before: { quantity: before.values.quantity ?? '' }, after: { quantity: quantity ?? '' } }] }];
  });
}

export function recentHistoryKey(metadata: WorkbookMetadata) {
  const edit = metadata.business?.recent_edits.at(-1);
  return edit ? `${edit.kind}:${edit.operation_id}:${edit.sequence ?? ''}` : '';
}

export function dismissedMetadata(options: {
  metadata: WorkbookMetadata; suggestion: NextEditSuggestion; operationId: string;
}): WorkbookMetadata {
  const { metadata, suggestion, operationId } = options;
  const business = metadata.business;
  if (!business) throw new Error('业务元数据缺失，无法记录拒绝');
  return { ...metadata, business: { ...business, local_revision: business.local_revision + 1,
    recent_edits: [...business.recent_edits, { operation_id: operationId, kind: 'dismiss',
      suggestion_id: suggestion.id, sequence: nextEditSequence(business.recent_edits),
      semantic_action_id: suggestion.semantic_action_id,
      business_context_fingerprint: suggestion.business_context_fingerprint,
    }] } };
}

export function acceptedEdit(options: {
  suggestion: NextEditSuggestion; operationId: string; previous: RecentBusinessEdit[];
}): RecentBusinessEdit {
  const { suggestion, operationId, previous } = options;
  const line = suggestion.line_bindings[0] ?? suggestion.removed_lines?.[0];
  const cell = suggestion.patches[0];
  return {
    operation_id: operationId, kind: 'accept', suggestion_id: suggestion.id,
    device_id: line?.device_id, requirement_id: line?.requirement_id,
    line_id: line?.line_id, sheet: cell?.sheet ?? line?.sheet, row: cell?.row ?? line?.row,
    sequence: nextEditSequence(previous), changes: suggestion.changes,
    semantic_action_id: suggestion.semantic_action_id,
    business_context_fingerprint: suggestion.business_context_fingerprint,
  };
}

export function nextEditSequence(edits: RecentBusinessEdit[]) {
  return edits.reduce((largest, edit, index) => Math.max(largest, edit.sequence ?? index), -1) + 1;
}

export function undoneEdit(journal: WorkbookEditJournal, previous: RecentBusinessEdit[]): RecentBusinessEdit {
  return { operation_id: journal.operation_id, kind: 'undo', suggestion_id: journal.suggestion_id,
    sequence: nextEditSequence(previous), semantic_action_id: journal.semantic_action_id,
    business_context_fingerprint: journal.business_context_fingerprint };
}
