import type { CellEdit, SheetRow } from './model';

export function reviewRows(edits: readonly CellEdit[], rows: readonly SheetRow[]) {
  const byDevice = new Map(rows.filter((row) => !row.kind || row.kind === 'device').map((row) => [row.deviceId ?? row.id, row]));
  return edits.map((edit) => {
    const row = byDevice.get(edit.deviceId);
    return { ...edit, name: row?.values[1] ?? '设备已移除', model: row?.values[2] ?? '',
      previous: row?.values[edit.column] ?? '' };
  });
}

export function reviseEdit(edits: readonly CellEdit[], target: CellEdit): CellEdit[] {
  return edits.map((edit) => edit.deviceId === target.deviceId && edit.column === target.column
    ? { ...edit, value: target.value } : edit);
}
