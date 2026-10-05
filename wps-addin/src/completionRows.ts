import type { UnresolvedWorkbookRow } from './businessTypes';
import type { SheetRow, WorkbookLine, WorkbookMetadata } from './types';
import { scanWorkbook } from './workbook.ts';
import { WorkbookBindings } from './workbookBindings.ts';

export interface CompletionRows {
  lines: WorkbookLine[]; unresolved: UnresolvedWorkbookRow[]; presentLineIds: Set<string>;
}

export function parseCompletionRows(rows: readonly SheetRow[], metadata: WorkbookMetadata): CompletionRows {
  const bindings = new WorkbookBindings(metadata.line_bindings);
  const result: CompletionRows = { lines: [], unresolved: [], presentLineIds: new Set() };
  for (const row of rows) {
    const matched = bindings.resolve(row);
    const known = matched ?? bindings.at(row);
    const duplicate = known && result.presentLineIds.has(known.line_id);
    if (known) result.presentLineIds.add(known.line_id);
    const scan = scanWorkbook([row], { ...metadata, line_bindings: matched ? [matched] : [] });
    if (scan.lines.length && !duplicate) { result.lines.push(...scan.lines); continue; }
    const scopes = metadata.business?.scopes.filter((s) => s.sheet === row.sheet
      && s.start_row <= row.row && s.end_row >= row.row) ?? [];
    const confirmed = known?.confirmed_values && !duplicate ? scanWorkbook([{ ...row,
      values: known.confirmed_values, formula_fields: [], merged_fields: [] }], {
      ...metadata, business: undefined, line_bindings: [known],
    }).lines[0] : undefined;
    result.unresolved.push({ sheet: row.sheet, row: row.row,
      line_id: duplicate ? undefined : known?.line_id, device_id: duplicate ? undefined : known?.device_id,
      system_id: scopes.length === 1 ? scopes[0].system_id : null,
      reason_code: duplicate ? 'duplicate_identity' : !matched ? 'identity_unconfirmed'
        : !known?.kind ? 'kind_unconfirmed' : row.formula_fields.length ? 'formula_business_value' : 'invalid_business_value',
      confirmed_line: confirmed });
  }
  return result;
}
