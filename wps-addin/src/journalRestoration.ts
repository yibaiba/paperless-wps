import type { WorkbookEditJournal } from './businessTypes';
import type { LineBinding, WorkbookMetadata } from './types';
import { undoneEdit } from './recentBusinessEdits.ts';

function same(left: unknown, right: unknown) { return JSON.stringify(left) === JSON.stringify(right); }
function identity(line?: LineBinding) {
  if (!line) return undefined;
  const { content_fingerprint: _, ...rest } = line;
  return rest;
}

export function restoredMetadata(metadata: WorkbookMetadata, journal: WorkbookEditJournal) {
  const before = journal.before;
  const after = journal.after;
  const changed = new Set([...before.line_bindings, ...after.line_bindings]
    .map((line) => line.line_id).filter((id) => !same(
      before.line_bindings.find((l) => l.line_id === id),
      after.line_bindings.find((l) => l.line_id === id),
    )));
  for (const id of changed) {
    const current = identity(metadata.line_bindings.find((l) => l.line_id === id));
    if (![before, after].some((s) => same(current, identity(s.line_bindings.find((l) => l.line_id === id))))) {
      throw new Error(`产品行 ${id} 的身份已变化，撤销未覆盖当前内容`);
    }
  }
  const business = metadata.business;
  if (!business) throw new Error('业务元数据缺失，无法恢复');
  const added = after.business?.operations.slice(before.business?.operations.length ?? 0) ?? [];
  const synced = (metadata.binding?.binding_revision ?? 0) > (journal.binding_revision ?? 0);
  const operations = [...business.operations];
  const deletedByGroup = new Set((after.business?.removed_lines ?? [])
    .filter((line) => !before.business?.removed_lines?.some((b) => b.line_id === line.line_id))
    .map((line) => line.line_id));
  if (synced) {
    if (!journal.inverse_business_operations) throw new Error('此旧操作缺少同步后的逆向业务记录，无法自动撤销');
    operations.push(...journal.inverse_business_operations);
  } else if (added.length) {
    const start = before.business?.operations.length ?? 0;
    if (same(operations.slice(start, start + added.length), added)) operations.splice(start, added.length);
    else if (!same(operations, before.business?.operations)) throw new Error('业务操作顺序已变化，未覆盖后续操作');
  }
  const previousRows = before.business?.row_requirements ?? [];
  const afterRows = after.business?.row_requirements ?? [];
  const rowKey = (r: typeof previousRows[number]) => `${r.sheet}:${r.row}`;
  const touchedRows = new Set([...previousRows, ...afterRows].map(rowKey).filter((key) => !same(
    previousRows.find((r) => rowKey(r) === key), afterRows.find((r) => rowKey(r) === key),
  )));
  for (const key of touchedRows) {
    const row = business.row_requirements?.find((r) => rowKey(r) === key);
    if (![previousRows, afterRows].some((rows) => same(row, rows.find((r) => rowKey(r) === key)))) {
      throw new Error('当前行用途已变化，撤销未覆盖新用途');
    }
  }
  return { ...metadata,
    line_bindings: [...metadata.line_bindings.filter((l) => !changed.has(l.line_id)),
      ...before.line_bindings.filter((l) => changed.has(l.line_id))],
    business: { ...business, operations, local_revision: business.local_revision + 1,
      unresolved_line_ids: [...new Set([...(business.unresolved_line_ids ?? []),
        ...(before.business?.unresolved_line_ids ?? []).filter((id) => !after.business?.unresolved_line_ids?.includes(id))])],
      removed_lines: (business.removed_lines ?? []).filter((line) => !deletedByGroup.has(line.line_id)),
      row_requirements: [...(business.row_requirements ?? []).filter((r) => !touchedRows.has(rowKey(r))),
        ...previousRows.filter((r) => touchedRows.has(rowKey(r)))],
      recent_edits: [...business.recent_edits, undoneEdit(journal, business.recent_edits)] },
  };
}
