import type { RefObject } from 'react';
import type { createUniver } from '@univerjs/presets';
import { SetRangeValuesMutation } from '@univerjs/preset-sheets-core';
import { interceptSheetCommand } from './commandBridge';
import { editableColumns, isDeviceRow, rowDeviceId, parseClipboard, pastedEdits, type CellEdit, type SheetRow } from './model';

type Runtime = ReturnType<typeof createUniver>;
export interface SheetProps {
  rows: SheetRow[]; busy: boolean;
  onEdit: (edits: CellEdit[], batch: boolean) => void;
  onSelect: (ids: string[]) => void;
  onImport?: (text: string) => void;
  onError: (message: string) => void;
  onUndo: () => void; onRedo: () => void;
}
export function bindSheetEvents(runtime: Runtime, context: {
  latest: RefObject<SheetProps>; projecting: RefObject<boolean>; failed: RefObject<boolean>;
}) {
  const { latest, projecting, failed } = context;
  const editing = { current: false };
  const rawEdit: { current: { row: number; column: number; value: string } | null } = { current: null };
  const { univerAPI } = runtime;
  const workbook = univerAPI.getActiveWorkbook()!;
  const worksheet = workbook.getActiveSheet();
  const publish = (values: CellEdit[], batch: boolean) => queueMicrotask(() => latest.current.onEdit(values, batch));
  const report = (error: unknown) => queueMicrotask(() => latest.current.onError(error instanceof Error ? error.message : String(error)));
  const projectHistory = (event: { cancel?: boolean }, action: () => void) => {
    if (editing.current) return;
    event.cancel = true;
    if (!latest.current.busy && !failed.current) queueMicrotask(action);
  };
  return [
    univerAPI.addEvent(univerAPI.Event.BeforeUndo, (event) => projectHistory(event, latest.current.onUndo)),
    univerAPI.addEvent(univerAPI.Event.BeforeRedo, (event) => projectHistory(event, latest.current.onRedo)),
    univerAPI.addEvent(univerAPI.Event.BeforeSheetEditStart, (event) => {
      if (latest.current.busy || failed.current || !editableColumns.has(event.column) || (!latest.current.rows[event.row - 1] || !isDeviceRow(latest.current.rows[event.row - 1]))) { event.cancel = true; return; }
      editing.current = true;
    }),
    univerAPI.addEvent(univerAPI.Event.BeforeSheetEditEnd, (event) => {
      rawEdit.current = event.isConfirm ? { row: event.row, column: event.column, value: event.value.toPlainText().replace(/\r?\n$/, '') } : null;
    }),
    univerAPI.addEvent(univerAPI.Event.SheetEditEnded, () => { editing.current = false; }),
    univerAPI.addEvent(univerAPI.Event.BeforeClipboardPaste, (event) => {
      event.cancel = true;
      if (latest.current.busy || failed.current) return;
      try {
        const range = worksheet.getActiveRange()?.getRange();
        if (!range || event.text == null) throw new Error('剪贴板没有可用文本，请粘贴矩形文本区域。');
        if (parseClipboard(event.text).some((row) => row.length >= 5) && latest.current.onImport) { latest.current.onImport(event.text); return; }
        publish(pastedEdits(latest.current.rows, { row: range.startRow, column: range.startColumn }, event.text), true);
      } catch (error) { report(error); }
    }),
    workbook.onSelectionChange((selections) => {
      const ids = latest.current.rows.filter((row, i) => isDeviceRow(row) && selections.some((r) => i + 1 >= r.startRow && i + 1 <= r.endRow)).map(rowDeviceId);
      latest.current.onSelect(ids);
    }),
    univerAPI.addEvent(univerAPI.Event.BeforeCommandExecute, (event) => {
      interceptSheetCommand(event, { projecting: projecting.current,
        busy: latest.current.busy || failed.current, rows: latest.current.rows, raw: rawEdit.current,
        onEdit: publish, onError: report });
      if (!projecting.current && event.id === SetRangeValuesMutation.id) rawEdit.current = null;
    }),
  ];
}
