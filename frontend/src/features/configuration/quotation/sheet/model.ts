import type { Configuration, Deployment, SupplyAllocation, Requirement, Room, System } from '../../types';
import type { QuotedPrice, QuotationOutput } from '../types';

export const columns = [
  { title: '序号', width: 52 }, { title: '产品名称', width: 160 },
  { title: '产品型号', width: 130 }, { title: '产品说明', width: 300 },
  { title: '数量', width: 76 }, { title: '单位', width: 60 },
  { title: '单价', width: 95 }, { title: '金额', width: 105 },
  { title: '品牌', width: 90 }, { title: '备注说明', width: 230 },
] as const;
export const PRICE_COLUMN = 6;
export const editableColumns = new Set([3, 4, PRICE_COLUMN, 9]);
export interface SheetRow { id: string; values: string[]; deviceId?: string; kind?: 'device' | 'section' | 'total' }
export const rowDeviceId = (row: SheetRow) => row.deviceId ?? row.id;
export const isDeviceRow = (row: SheetRow) => !row.kind || row.kind === 'device';
export interface CellEdit { row: number; column: number; value: string; deviceId: string }
export type EditOperation =
  | { action: "price_versions_adopt"; adoption_date: string; items: { device_id: string; price: { id: string; revision: number } }[]; fingerprint: string }
  | { action: "room_put"; value: Room }
  | { action: "system_put"; value: System }
  | { action: "requirement_put"; value: Requirement }
  | { action: 'purchase_set'; device_id: string; quantity: string; evidence: string }
  | { action: 'description_set'; device_id: string; text: string | null }
  | { action: 'device_put'; value: Omit<Deployment, 'variant_snapshot' | 'source_snapshot' | 'origin_suggestion'> }
  | { action: 'device_patch'; device_id: string; quantity?: string; note?: string }
  | { action: 'section_set'; device_id: string; section: string }
  | { action: 'price_set'; value: QuotedPrice }
  | { action: 'supply_set'; device_id: string; allocations: SupplyAllocation[] };
export type SortOrder = 'original' | 'name' | 'section';

const defaultSections = ['无纸化会议系统', '会议扩声系统', '其他辅助设备'];

export function sheetRows(config: Configuration, output: QuotationOutput | null | undefined, sort: SortOrder): SheetRow[] {
  if (!output) return [];
  const devices = new Map(config.devices.map((device) => [device.id, device]));
  const groups = new Map<string, typeof output.lines>(defaultSections.map((name) => [name, []]));
  for (const line of output.lines) {
    // Match export inclusion exactly: existing-only equipment stays in the supply panel.
    if (!devices.has(line.device_id) || (!positive(line.purchase_quantity) && !positive(line.unknown_quantity))) continue;
    const group = groups.get(line.section) ?? [];
    group.push(line); groups.set(line.section, group);
  }
  const rows: SheetRow[] = [];
  let number = 0;
  for (const [section, lines] of groups) {
    rows.push({ id: `section:${section}`, kind: 'section', values: [section, '', '', '', '', '', '', '', '', ''] });
    const ordered = sort === 'name' ? [...lines].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN') || a.device_id.localeCompare(b.device_id)) : lines;
    for (const line of ordered) {
      const pendingOnly = !positive(line.purchase_quantity) && positive(line.unknown_quantity);
      const notes = line.note;
      rows.push({ id: `device:${line.device_id}`, deviceId: line.device_id, kind: 'device', values: [
        String(++number), line.name, line.model, line.specification,
        pendingOnly ? '' : line.purchase_quantity, line.unit, line.unit_price ?? '',
        pendingOnly ? '' : line.amount ?? '', line.brand, notes,
      ] });
    }
  }
  rows.push({ id: 'quote:total', kind: 'total', values: ['报价合计', '', '', '', '', '', '', output.total ?? '待确认', '', ''] });
  return rows;
}

function positive(value: string) { return /^\d*(?:\.\d*)?$/.test(value) && /[1-9]/.test(value); }

export function cellEdit(rows: SheetRow[], row: number, column: number, value: string): CellEdit {
  if (!rows[row - 1] || !isDeviceRow(rows[row - 1]) || !editableColumns.has(column)) throw new Error(`${address(row, column)} 为只读单元格，请使用产品或供货面板。`);
  return { row, column, value, deviceId: rowDeviceId(rows[row - 1]) };
}
export function address(row: number, column: number) { return `${String.fromCharCode(65 + column)}${row + 1}`; }
function numberText(edit: CellEdit) {
  const text = edit.value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(text)) {
    throw new Error(`${address(edit.row, edit.column)}：请输入非负数值，不接受公式或空值。`);
  }
  return text;
}
function priceOperation(device: Deployment, value: string, evidence: string): EditOperation {
  if (!evidence.trim()) throw new Error('修改单价必须填写调整依据。');
  return { action: 'price_set', value: { device_id: device.id, variant_id: device.variant_id,
    source_id: device.source_id, mode: 'manual', price_column: '', unit_price: value, evidence: evidence.trim() } };
}
export function editOperations(config: Configuration, edits: CellEdit[], evidence: string): EditOperation[] {
  return edits.map((edit) => {
    const device = config.devices.find((item) => item.id === edit.deviceId);
    if (!device) throw new Error(`${address(edit.row, edit.column)}：设备已删除，请重新编辑。`);
    if (!config.quotation) throw new Error('请先填写报价资料。');
    if (edit.value.trim().startsWith('=')) throw new Error(`${address(edit.row, edit.column)}：不接受公式。`);
    if (edit.column === 3) return { action: 'description_set', device_id: device.id, text: edit.value };
    if (edit.column === 9) return { action: 'device_patch', device_id: device.id, note: edit.value };
    if (edit.column === 4) return { action: 'purchase_set', device_id: device.id, quantity: numberText(edit), evidence: '报价工作表明确修改本次采购数量' };
    if (edit.column === PRICE_COLUMN) return priceOperation(device, numberText(edit), evidence);
    throw new Error(`${address(edit.row, edit.column)}：只读列不能修改。`);
  });
}

// Excel quotes fields containing tabs/newlines and doubles embedded quotes.
export function parseClipboard(text: string): string[][] {
  const rows: string[][] = [], row: string[] = [];
  let value = '', quoted = false;
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (character === '"' && (quoted || value === '')) {
      if (quoted && text[index + 1] === '"') { value += '"'; index++; }
      else quoted = !quoted;
    } else if (!quoted && (character === '\t' || character === '\n' || character === '\r')) {
      row.push(value); value = '';
      if (character !== '\t') {
        rows.push([...row]); row.length = 0;
        if (character === '\r' && text[index + 1] === '\n') index++;
      }
    } else value += character;
  }
  if (quoted) throw new Error('粘贴文本存在未闭合的引号。');
  if (value || row.length || !rows.length) { row.push(value); rows.push([...row]); }
  return rows;
}
export function pastedEdits(rows: SheetRow[], start: { row: number; column: number }, text: string): CellEdit[] {
  return parseClipboard(text).flatMap((values, offset) => values.map((value, column) =>
    cellEdit(rows, start.row + offset, start.column + column, value)));
}
