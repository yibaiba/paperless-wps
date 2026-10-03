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
  const started = performance.now();
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
  const changedIds = new Set([...suggestion.line_bindings, ...(suggestion.removed_lines ?? [])].map((line) => line.line_id));
  const after = {
    line_bindings: [...metadata.line_bindings.filter((line) => !changedIds.has(line.line_id)),
      ...suggestion.line_bindings],
    business: { ...metadata.business, local_revision: suggestion.local_revision + 1,
      unresolved_line_ids: metadata.business.unresolved_line_ids?.filter((id) => !suggestion.confirmed_identity_ids?.includes(id)),
      row_requirements: suggestion.row_requirements ?? metadata.business.row_requirements,
      removed_lines: [...(metadata.business.removed_lines ?? []), ...(suggestion.removed_lines ?? [])],
      operations: [...metadata.business.operations, ...suggestion.business_operations],
      recent_edits: [...metadata.business.recent_edits, {
        operation_id: operationId, kind: 'accept' as const, suggestion_id: suggestion.id,
        device_id: suggestion.line_bindings[0]?.device_id ?? suggestion.removed_lines?.[0]?.device_id,
        requirement_id: suggestion.line_bindings[0]?.requirement_id,
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
    businessDiagnostic(host, { event_id: `${operationId}:accepted`, event_type: 'completion_accepted',
      outcome: 'success', duration_ms: Math.round(performance.now() - started) });
    if (journal.before.line_bindings.some((line) => suggestion.line_bindings.some((after) => after.line_id === line.line_id && after.variant_id !== line.variant_id))) {
      businessDiagnostic(host, { event_id: `${operationId}:replaced`, event_type: 'completion_replaced', outcome: 'success' });
    }
    return next;
  } catch (reason) {
    const error = reason instanceof Error ? reason.message : String(reason);
    try { restoreJournal(host, journal, false); }
    catch (recovery) {
      const saved = host.journals().find((j) => j.operation_id === operationId) ?? journal;
      host.writeJournal({ ...saved, state: 'recovery_required', error: `${error}；${recovery}` });
      throw new Error(`写入失败且恢复未完成：${error}；${recovery}`);
    }
    throw new Error(`写入失败，已恢复本次修改：${error}`);
  }
}

export function restoreJournal(host: JournalHost, journal: WorkbookEditJournal, undo = true) {
  const metadata = host.readMetadata();
  if (metadata.pending_sync) throw new Error('请先恢复未完成的同步回执，再撤销本地修改');
  if (undo && !journal.recovery) checkCells(host, journal.patches, 'after');
  const recovery = journal.recovery ?? {
    intent: undo ? 'undo' as const : 'rollback' as const,
    before: metadata, after: restoredMetadata(metadata, journal),
  };
  if (![recovery.before, recovery.after].some((value) => JSON.stringify(value) === JSON.stringify(metadata))) {
    throw new Error('恢复期间业务元数据已变化，请核对冲突；未覆盖新设置');
  }
  // Validate the entire rollback before touching a cell, including protected cells.
  for (const patch of journal.patches) {
    const cell = host.readCell(patch);
    assertWritableTargets([{ ...cell, address: `${cell.sheet} ${cell.row}:${cell.column}` }]);
    if (cell.value !== patch.before && cell.value !== patch.after) {
      throw new Error(`${cell.sheet} ${cell.row}:${cell.column} 恢复冲突，保留当前值`);
    }
  }
  const pending = { ...journal, state: 'recovery_required' as const, recovery };
  host.writeJournal(pending);
  try {
    for (const patch of [...journal.patches].reverse()) {
      const cell = host.readCell(patch);
      if (cell.value === patch.before) continue;
      if (cell.value !== patch.after) throw new Error(`${patch.sheet} ${patch.row}:${patch.column} 恢复冲突，保留当前值`);
      try { host.writeCellValue(cell, patch.before); }
      catch (reason) { throw new Error(`${patch.sheet} ${patch.row}:${patch.column} 恢复未完成：${reason}`); }
    }
    checkCells(host, journal.patches, 'before');
    host.writeMetadata(recovery.after);
    host.writeJournal({ ...journal, recovery: undefined, state: recovery.intent === 'undo' ? 'undone' : 'restored' });
  } catch (reason) {
    host.writeJournal({ ...pending, error: String(reason) });
    throw reason;
  }
  if (recovery.intent === 'undo') businessDiagnostic(host, { event_id: `${journal.operation_id}:undone`, event_type: 'completion_undone', outcome: 'restored' });
  return host.readMetadata();
}
