import { CommandType, type ICellData } from '@univerjs/core';
import { SetRangeValuesMutation, type ISetRangeValuesMutationParams } from '@univerjs/preset-sheets-core';
import { address, cellEdit, type CellEdit, type SheetRow } from './model';

export interface CommandEvent { id: string; type?: number; params?: unknown; cancel?: boolean }
export interface CommandContext {
  projecting: boolean; busy: boolean; rows: SheetRow[];
  raw: { row: number; column: number; value: string } | null;
  onEdit: (edits: CellEdit[], batch: boolean) => void;
  onError: (error: unknown) => void;
}
const viewMutations = new Set([
  'sheet.mutation.set-worksheet-col-width', 'sheet.mutation.set-worksheet-row-height',
  'sheet.mutation.set-worksheet-row-is-auto-height', 'sheet.mutation.set-worksheet-row-auto-height',
]);
function mutationEdits(params: ISetRangeValuesMutationParams, context: CommandContext) {
  return Object.entries(params.cellValue ?? {}).flatMap(([r, values]) => Object.entries(values).map(([c, value]) => {
    const row = Number(r), column = Number(c), { raw } = context;
    const cell = value as ICellData | null;
    if (cell && !['v', 'p', 'f'].some((key) => Object.hasOwn(cell, key))) {
      throw new Error(`${address(row, column)}：单元格格式由报价布局管理，请只编辑业务值。`);
    }
    const text = raw?.row === row && raw.column === column ? raw.value : String(cell?.v ?? '');
    return cellEdit(context.rows, row, column, text);
  }));
}
export function interceptSheetCommand(event: CommandEvent, context: CommandContext) {
  if (context.projecting) return;
  if (event.id === SetRangeValuesMutation.id) {
    event.cancel = true;
    if (context.busy) return;
    try {
      const edits = mutationEdits(event.params as ISetRangeValuesMutationParams, context);
      if (edits.length) context.onEdit(edits, edits.length > 1);
    } catch (error) { context.onError(error); }
    return;
  }
  if (event.type === CommandType.MUTATION && event.id.startsWith('sheet.mutation.') && !viewMutations.has(event.id)) {
    event.cancel = true;
    context.onError(new Error('产品和采购结构请通过业务面板修改；排序请使用工作表上方的排序选项。'));
  }
}
