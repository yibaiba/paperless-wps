import { WorkbookRowIndex } from '../src/workbookRowIndex.ts';
import { completionRequest } from '../src/businessWorkbook.ts';

export function contextWorkload(count = 1000) {
  const metrics = { fullReads: 0, rowReads: 0, bindingReads: 0 };
  const rows = Array.from({ length: count }, (_, i) => ({ sheet: 'q', row: i + 2,
    values: { model: `m${i}`, name: `n${i}`, quantity: '1' }, formula_fields: [], merged_fields: [] }));
  const metadata = { schema_version: 2, profile_revision: 1,
    binding: { binding_id: 'b', binding_revision: 1, draft_revision: 1, base_revision: 0, managed_device_ids: [] },
    line_bindings: rows.map((row) => ({ line_id: String(row.row),
      get sheet() { metrics.bindingReads++; return 'q'; }, row: row.row,
      variant_id: 'v', source_id: 's', kind: 'software', confirmed_values: row.values,
      anchor_fingerprint: `${row.values.model}\0${row.values.name}` })),
    business: { local_revision: 0, scopes: [{ sheet: 'q', start_row: 2, end_row: count + 2,
      room_id: 'room', system_id: 's' }], operations: [], recent_edits: [] } };
  const host = { readRow: (_, row) => { metrics.rowReads++; return rows[row - 2] ?? {
    sheet: 'q', row, values: {}, formula_fields: [], merged_fields: [] }; },
    readRows: () => { metrics.fullReads++; return rows; }, businessRevision: () => metadata.business.local_revision };
  const profile = { id: 'p', revision: 1, sheet_selector: 'q', managed_fields: ['model', 'name'] };
  const index = new WorkbookRowIndex(host, profile);
  const request = (query = 'm0') => completionRequest({ host, index, profile, metadata,
    cell: { sheet: 'q', row: 2, column: 1 }, query });
  return { metrics, rows, metadata, host, profile, index, request };
}
