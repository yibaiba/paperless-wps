import type { HostAdapter } from './host';
import type { WorkbookRowIndex } from './workbookRowIndex';
import type { ActiveCell, TemplateProfile, WorkbookLine, WorkbookMetadata } from './types';
import { bindingForRow, scanWorkbook } from './workbook.ts';
import { observedQuantityEdits } from './recentBusinessEdits.ts';
import { availableProductTarget } from './businessTargets.ts';
import { parseCompletionRows } from './completionRows.ts';

export function businessSyncRequest(metadata: WorkbookMetadata, lines: WorkbookLine[], options: {
  presentLineIds?: ReadonlySet<string>;
} = {}) {
  const binding = metadata.binding;
  if (!binding) throw new Error('请先绑定项目');
  const visible = options.presentLineIds ?? new Set(lines.map((line) => line.line_id));
  const missing = metadata.schema_version === 2 ? metadata.line_bindings.filter((b) => !visible.has(b.line_id) && b.confirmed_values) : [];
  const removed = scanWorkbook(missing.map((b) => ({ sheet: b.sheet, row: b.row,
    values: b.confirmed_values!, formula_fields: [], merged_fields: [] })), metadata);
  if (removed.unresolved.length) throw new Error(removed.unresolved.join('；'));
  return {
    schema_version: metadata.schema_version, binding_id: binding.binding_id,
    expected_binding_revision: binding.binding_revision,
    expected_draft_revision: binding.draft_revision,
    expected_project_revision: binding.base_revision,
    template_profile_revision: metadata.profile_revision,
    known_device_ids: binding.managed_device_ids, lines,
    business_operations: metadata.business?.operations ?? [],
    removed_lines: [...new Map([...(metadata.business?.removed_lines ?? []), ...removed.lines]
      .filter((line) => !visible.has(line.line_id)).map((line) => [line.line_id, line])).values()],
  };
}

export function completionRequest(options: {
  host: HostAdapter; profile: TemplateProfile; metadata: WorkbookMetadata;
  cell: ActiveCell; index: WorkbookRowIndex; query: string;
}) {
  const { host, profile, metadata, cell, index, query } = options;
  const business = metadata.business;
  const scopes = business?.scopes.filter((s) => s.sheet === cell.sheet
    && s.start_row <= cell.row && s.end_row >= cell.row) ?? [];
  if (scopes.length !== 1) throw new Error('请在项目业务设置中明确当前行的房间、系统与业务区');
  const scope = scopes[0];
  const active = index.refresh(cell.row);
  const currentBinding = bindingForRow(active, metadata.line_bindings)
    ?? metadata.line_bindings.find((b) => b.sheet === cell.sheet && b.row === cell.row);
  const rows = index.read().flatMap((row) => {
    if (row.row !== cell.row) return [row];
    if (!currentBinding || (!query && !row.values.model?.trim() && !row.values.name?.trim())) return [];
    if (!currentBinding.confirmed_values) return [row];
    return [{ ...row, values: { ...row.values,
      model: currentBinding.confirmed_values.model, name: currentBinding.confirmed_values.name } }];
  });
  const scanned = parseCompletionRows(rows, metadata);
  const targetRows = new Set(scanned.lines.filter((b) => b.sheet === scope.sheet
    && b.row >= scope.start_row && b.row <= scope.end_row).map((b) => b.row));
  const cached = new Map(index.read().map((row) => [row.row, row]));
  const free = availableProductTarget({ scope, activeRow: cell.row, profile,
    occupied: new Set(cached.keys()), readRow: (row) => index.peek(row) });
  if (free) { cached.set(free.row, free); targetRows.add(free.row); }
  const target_cells = [...targetRows].filter((row) => row !== cell.row).map((row) => ({
    ...(cached.get(row) ?? index.refresh(row)), column: cell.column,
  }));
  return {
    ...businessSyncRequest(metadata, scanned.lines, { presentLineIds: scanned.presentLineIds }),
    unresolved_rows: scanned.unresolved, local_revision: host.businessRevision(),
    scope: { ...scope, requirement_id: currentBinding?.requirement_id
      ?? business?.row_requirements?.find((r) => r.sheet === cell.sheet && r.row === cell.row)?.requirement_id
      ?? scope.requirement_id },
    active_cell: { ...active, column: cell.column }, target_cells, query,
    recent_edits: [...business?.recent_edits ?? [], ...observedQuantityEdits(index, metadata)],
  };
}
