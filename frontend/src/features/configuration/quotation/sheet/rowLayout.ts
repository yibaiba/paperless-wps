import type { SheetRow } from './model';
import type { createUniver } from '@univerjs/presets';
import { AddWorksheetMergeMutation, RemoveWorksheetMergeMutation, SetWorksheetRowHeightMutation, SetWorksheetRowIsAutoHeightMutation } from '@univerjs/preset-sheets-core';

import { rowLayout } from './templateLayout';
export { rowLayout, DETAIL_HEIGHT } from './templateLayout';

export function updateRowLayout(runtime: ReturnType<typeof createUniver>, rows: readonly SheetRow[], remove = false) {
  const { univerAPI } = runtime;
  const workbook = univerAPI.getActiveWorkbook()!, sheet = workbook.getActiveSheet();
  const target = { unitId: workbook.getId(), subUnitId: sheet.getSheetId() };
  const layout = rowLayout(rows);
  if (layout.mergeData.length && !univerAPI.syncExecuteCommand(remove ? RemoveWorksheetMergeMutation.id : AddWorksheetMergeMutation.id,
    { ...target, ranges: layout.mergeData })) throw new Error('工作表分区合并区域更新失败');
  // Fixed template heights must disable the SDK's cached automatic heights too.
  if (!remove && !univerAPI.syncExecuteCommand(SetWorksheetRowIsAutoHeightMutation.id, {
    ...target, ranges: [{ startRow: 0, endRow: rows.length, startColumn: 0, endColumn: 9 }], autoHeightInfo: 0,
  })) throw new Error('工作表固定行高设置失败');
  if (!remove && rows.length && !univerAPI.syncExecuteCommand(SetWorksheetRowHeightMutation.id, {
    ...target, ranges: [{ startRow: 0, endRow: rows.length, startColumn: 0, endColumn: 9 }],
    rowHeight: Object.fromEntries(Object.entries(layout.rowData).map(([index, row]) => [index, row.h])),
  })) throw new Error('工作表分区行高更新失败');
}
