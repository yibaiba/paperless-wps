import { CellValueType, WrapStrategy, VerticalAlign, type ICellData, type IObjectMatrixPrimitiveType } from '@univerjs/core';
import { editableColumns } from './model';
import type { ProjectionMatrix } from './projection';
import type { createUniver } from '@univerjs/presets';
import { SetRangeValuesCommand, SetWorksheetRowCountCommand } from '@univerjs/preset-sheets-core';

export function projectionPort(runtime: ReturnType<typeof createUniver>) {
  const { univerAPI } = runtime;
  const workbook = univerAPI.getActiveWorkbook()!, sheet = workbook.getActiveSheet();
  const target = { unitId: workbook.getId(), subUnitId: sheet.getSheetId() };
  return {
    resize: (rowCount: number) => univerAPI.syncExecuteCommand(SetWorksheetRowCountCommand.id, { ...target, rowCount }),
    write: (cells: ProjectionMatrix) => univerAPI.syncExecuteCommand(SetRangeValuesCommand.id, { ...target, range: cellBounds(cells), value: sdkCells(cells) }),
  };
}

function cellBounds(cells: ProjectionMatrix) {
  const rows = Object.keys(cells).map(Number);
  const columns = Object.values(cells).flatMap((row) => Object.keys(row).map(Number));
  return { startRow: Math.min(...rows), endRow: Math.max(...rows), startColumn: Math.min(...columns), endColumn: Math.max(...columns) };
}

export function sdkCells(matrix: ProjectionMatrix): IObjectMatrixPrimitiveType<ICellData> {
  return Object.fromEntries(Object.entries(matrix).map(([row, cells]) => [row,
    Object.fromEntries(Object.entries(cells).map(([column, cell]) => [column, {
      v: cell.value, t: CellValueType.STRING, f: null, p: null,
      ...(cell.style === 'header' || cell.style === 'section' || cell.style === 'total' ? { s: { bg: { rgb: '#EAF0FA' }, bl: 1, tb: WrapStrategy.CLIP, vt: VerticalAlign.MIDDLE } }
        : cell.style === 'body' ? { s: { bl: 0, bg: { rgb: editableColumns.has(Number(column)) ? '#FFFFFF' : '#FAFBFC' }, tb: WrapStrategy.WRAP, vt: VerticalAlign.TOP } } : {}),
    } as ICellData])),
  ]));
}
