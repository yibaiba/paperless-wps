import type { ImportRow, Mapping } from './model';

export interface MergedRegion {
  range: string;
  start_row: number; end_row: number;
  start_column: number; end_column: number;
}

export function withMergedNotes(rows: ImportRow[], context: {
  matrix: string[][]; header: number; mapping: Mapping; merges: MergedRegion[];
}): ImportRow[] {
  const noteColumn = context.mapping.note;
  if (noteColumn === undefined) return rows;
  const notes = new Map<number, { value: string; range: string }>();
  for (const region of context.merges) {
    if (region.start_column !== noteColumn + 1 || region.end_column !== region.start_column
      || region.start_row <= context.header + 1 || region.end_row === region.start_row) continue;
    const value = context.matrix[region.start_row - 1]?.[noteColumn] ?? '';
    if (!value.trim()) continue;
    for (let row = region.start_row; row <= Math.min(region.end_row, context.matrix.length); row++) {
      notes.set(row, { value, range: region.range });
    }
  }
  return rows.map((row) => {
    const shared = notes.get(row.sourceRow);
    return shared ? { ...row, note: row.note || shared.value, mergedNoteRange: shared.range } : row;
  });
}
