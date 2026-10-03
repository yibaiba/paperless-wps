import type { CellPatch, NextEditSuggestion, WorkbookEditJournal } from './businessTypes';
import type { ActiveCell, WorkbookMetadata } from './types';
import { assertWritableTargets } from './workbook.ts';
import { restoredMetadata } from './journalRestoration.ts';
import { businessDiagnostic } from './businessDiagnostics.ts';
import type { DiagnosticEventInput } from './types';

export interface JournalHost {
  readCell(cell: Pick<ActiveCell, 'sheet' | 'row' | 'column'>): ActiveCell;
  writeCellValue(cell: ActiveCell, value: string): void;
  readMetadata(): WorkbookMetadata;
  writeMetadata(metadata: WorkbookMetadata): void;
  journals(): WorkbookEditJournal[];
  writeJournal(journal: WorkbookEditJournal): void;
  businessRevision?(): number;
  recordDiagnostic?(value: DiagnosticEventInput): unknown;
  reportBackgroundError?(message: string): void;
}

function snapshot(metadata: WorkbookMetadata, lineIds: Set<string>) {
  return { line_bindings: metadata.line_bindings.filter((line) => lineIds.has(line.line_id)), business: metadata.business };
}

function checkCells(host: JournalHost, patches: CellPatch[], side: 'before' | 'after') {
  const cells = patches.map((patch) => host.readCell(patch));
  assertWritableTargets(cells.map((cell) => ({ ...cell, address: `${cell.sheet} 第 ${cell.row} 行` })));
  patches.forEach((patch, index) => {
    if (cells[index].value !== patch[side]) throw new Error(`第 ${patch.row} 行已被修改，请重新预览`);
  });
}

export function applyNextEdit(options: {
  host: JournalHost; suggestion: NextEditSuggestion; operationId: string;
}) {
  const { host, suggestion, operationId } = options;
  const previous = host.journals().find((j) => j.operation_id === operationId);
  if (previous) {
    if (previous.state === 'applied') return host.readMetadata();
    throw new Error('此操作尚未完成，请先恢复编辑日志');
  }
  const metadata = host.readMetadata();
  if (metadata.pending_sync) throw new Error('请先恢复未完成的同步回执，再应用新的业务修改');
  if (host.journals().some((j) => ['prepared', 'recovery_required'].includes(j.state))) {
    throw new Error('工作簿存在未完成的修改，请先恢复编辑日志');
  }
  const revision = host.businessRevision?.() ?? metadata.business?.local_revision;
  if (!metadata.business || revision !== suggestion.local_revision) {
    throw new Error('工作簿上下文已变化，请重新预览');
  }
  if (!suggestion.applicable) throw new Error('此建议还有未解决的问题，尚不能应用');
  checkCells(host, suggestion.patches, 'before');
  const changedIds = new Set(suggestion.line_bindings.map((line) => line.line_id));
  const after = {
    line_bindings: [...metadata.line_bindings.filter((line) => !changedIds.has(line.line_id)),
      ...suggestion.line_bindings],
    business: { ...metadata.business, local_revision: suggestion.local_revision + 1,
      row_requirements: suggestion.row_requirements ?? metadata.business.row_requirements,
      operations: [...metadata.business.operations, ...suggestion.business_operations],
      recent_edits: [...metadata.business.recent_edits, {
        operation_id: operationId, kind: 'accept' as const, suggestion_id: suggestion.id,
      }] },
  };
  const journal: WorkbookEditJournal = {
    operation_id: operationId, suggestion_id: suggestion.id, created_at: new Date().toISOString(),
    state: 'prepared', patches: suggestion.patches, before: snapshot(metadata, changedIds),
    after: { ...after, line_bindings: suggestion.line_bindings },
    binding_revision: metadata.binding?.binding_revision ?? 0,
    inverse_business_operations: suggestion.inverse_business_operations ?? [],
  };
  host.writeJournal(journal);
  try {
    for (const patch of journal.patches) {
      host.writeCellValue(host.readCell(patch), patch.after);
    }
    checkCells(host, journal.patches, 'after');
    const next = { ...metadata, schema_version: 2 as const, ...after };
    host.writeMetadata(next);
    host.writeJournal({ ...journal, state: 'applied' });
    businessDiagnostic(host, { event_id: `${operationId}:accepted`, event_type: 'completion_accepted', outcome: 'success' });
    if (journal.before.line_bindings.some((line) => suggestion.line_bindings.some((after) => after.line_id === line.line_id && after.variant_id !== line.variant_id))) {
      businessDiagnostic(host, { event_id: `${operationId}:replaced`, event_type: 'completion_replaced', outcome: 'success' });
    }
    return next;
  } catch (reason) {
    const error = reason instanceof Error ? reason.message : String(reason);
    try { restoreJournal(host, journal, false); }
    catch (recovery) {
      host.writeJournal({ ...journal, state: 'recovery_required', error: `${error}；${recovery}` });
      throw new Error(`写入失败且恢复未完成：${error}；${recovery}`);
    }
    throw new Error(`写入失败，已恢复本次修改：${error}`);
  }
}

export function restoreJournal(host: JournalHost, journal: WorkbookEditJournal, undo = true) {
  const metadata = host.readMetadata();
  if (metadata.pending_sync) throw new Error('请先恢复未完成的同步回执，再撤销本地修改');
  if (undo) checkCells(host, journal.patches, 'after');
  const restored = restoredMetadata(metadata, journal);
  // Validate the entire rollback before touching a cell, including protected cells.
  for (const patch of journal.patches) {
    const cell = host.readCell(patch);
    assertWritableTargets([{ ...cell, address: `${cell.sheet} ${cell.row}:${cell.column}` }]);
    if (cell.value !== patch.before && cell.value !== patch.after) {
      throw new Error(`${cell.sheet} ${cell.row}:${cell.column} 恢复冲突，保留当前值`);
    }
  }
  for (const patch of [...journal.patches].reverse()) {
    const cell = host.readCell(patch);
    if (cell.value === patch.before) continue;
    if (cell.value !== patch.after) throw new Error(`第 ${patch.row} 行恢复冲突，保留当前值`);
    host.writeCellValue(cell, patch.before);
  }
  checkCells(host, journal.patches, 'before');
  host.writeMetadata(restored);
  host.writeJournal({ ...journal, state: undo ? 'undone' : 'restored' });
  if (undo) businessDiagnostic(host, { event_id: `${journal.operation_id}:undone`, event_type: 'completion_undone', outcome: 'restored' });
  return host.readMetadata();
}
