import type { SheetRow } from './model';

export interface ProjectionCell { readonly value: string; readonly style: 'header' | 'body' | 'section' | 'total' | null }
export type ProjectionMatrix = Record<number, Record<number, ProjectionCell>>;
export interface ProjectionLayout { readonly titles: readonly string[]; readonly minimumRows: number }
export interface ProjectionPlan {
  readonly rowCount: number;
  readonly resized: boolean;
  readonly reordered: boolean;
  readonly cellCount: number;
  readonly cells: ProjectionMatrix;
}
const rowCount = (rows: readonly SheetRow[], layout: ProjectionLayout) => Math.max(layout.minimumRows, rows.length + 1);

export function initialProjection(rows: readonly SheetRow[], layout: ProjectionLayout): ProjectionPlan {
  const cells: ProjectionMatrix = { 0: Object.fromEntries(layout.titles.map((value, col) => [col, { value, style: 'header' }])) };
  rows.forEach((row, index) => {
    cells[index + 1] = Object.fromEntries(layout.titles.map((_, col) => [col, { value: row.values[col] ?? '', style: row.kind === 'section' || row.kind === 'total' ? row.kind : 'body' }]));
  });
  return { rowCount: rowCount(rows, layout), resized: false, reordered: false, cellCount: (rows.length + 1) * layout.titles.length, cells };
}

export function diffProjection(previous: readonly SheetRow[], rows: readonly SheetRow[], layout: ProjectionLayout): ProjectionPlan {
  const count = rowCount(rows, layout), cells: ProjectionMatrix = {};
  const previousById = new Map(previous.map((row) => [row.id, row]));
  let cellCount = 0;
  const end = Math.min(Math.max(previous.length, rows.length), count - 1);
  for (let index = 0; index < end; index++) {
    const row = rows[index], oldPosition = previous[index];
    const old = row && previousById.get(row.id);
    const moved = row?.id !== oldPosition?.id;
    layout.titles.forEach((_, column) => {
      const value = row?.values[column] ?? '';
      const styleChanged = row?.kind !== oldPosition?.kind;
      if (!moved && !styleChanged && (old?.values[column] ?? '') === value) return;
      if (!row && !oldPosition) return;
      (cells[index + 1] ??= {})[column] = { value, style: index >= previous.length || styleChanged ? (row?.kind === 'section' || row?.kind === 'total' ? row.kind : 'body') : null };
      cellCount++;
    });
  }
  return { rowCount: count, resized: count !== rowCount(previous, layout),
    reordered: previous.length !== rows.length || rows.some((row, index) => row.id !== previous[index]?.id), cellCount, cells };
}

export function snapshotRows(rows: readonly SheetRow[]): SheetRow[] {
  return rows.map((row) => ({ ...row, values: [...row.values] }));
}

export function applyProjection(plan: ProjectionPlan, port: {
  resize: (count: number) => boolean;
  write: (cells: ProjectionMatrix) => boolean;
}) {
  if (plan.resized && !port.resize(plan.rowCount)) throw new Error('Univer 未完成行数调整');
  if (plan.cellCount && !port.write(plan.cells)) throw new Error('Univer 未完成单元格更新');
}
