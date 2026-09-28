import type { SheetRow } from './model';

export const DETAIL_HEIGHT = 92;
export function rowLayout(rows: readonly SheetRow[]) {
  const mergeData = rows.flatMap((row, i) => row.kind === 'section' || row.kind === 'total'
    ? [{ startRow: i + 1, endRow: i + 1, startColumn: 0, endColumn: row.kind === 'section' ? 9 : 6 }] : []);
  const rowData = Object.fromEntries(rows.map((row, i) => [i + 1, { ia: 0 as const, h: row.kind === 'section' || row.kind === 'total' ? 32 : DETAIL_HEIGHT }]));
  return { mergeData, rowData: { 0: { h: 34, ia: 0 as const }, ...rowData } };
}
