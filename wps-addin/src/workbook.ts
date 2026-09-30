import type {
  LineBinding, SheetRow, TemplateField, WorkbookLine, WorkbookMetadata,
} from './types';

const NUMBER = /^\d+(?:\.\d+)?$/;

export interface WritableTarget {
  address: string;
  formula: string;
  merged: boolean;
}

export function assertWritableTargets(targets: WritableTarget[]) {
  const formula = targets.find((target) => target.formula.trim().startsWith('='));
  if (formula) throw new Error(`${formula.address} 含公式，插件没有写入`);
  const merged = targets.find((target) => target.merged);
  if (merged) throw new Error(`${merged.address} 属于合并区域，插件没有写入`);
}

function value(row: SheetRow, field: TemplateField) { return row.values[field]?.trim() ?? ''; }

export function rowAnchor(row: SheetRow) {
  return [value(row, 'model'), value(row, 'name')]
    .join('\0').toLocaleLowerCase();
}

export function bindingForRow(row: SheetRow, bindings: LineBinding[]) {
  const exact = bindings.find((item) => item.sheet === row.sheet && item.row === row.row);
  if (exact && (!exact.anchor_fingerprint || exact.anchor_fingerprint === rowAnchor(row))) return exact;
  const matches = bindings.filter((item) => item.anchor_fingerprint === rowAnchor(row));
  return matches.length === 1 ? matches[0] : undefined;
}

export function scanWorkbook(rows: SheetRow[], metadata: WorkbookMetadata) {
  const lines: WorkbookLine[] = [];
  const unresolved: string[] = [];
  for (const row of rows) {
    const binding = bindingForRow(row, metadata.line_bindings);
    if (!binding) {
      unresolved.push(`${row.sheet} 第 ${row.row} 行尚未确认具体产品配置`);
      continue;
    }
    if (row.formula_fields.includes('quantity') || row.formula_fields.includes('price')) {
      unresolved.push(`${row.sheet} 第 ${row.row} 行数量或价格是公式，请先转换为值`);
      continue;
    }
    const quantity = value(row, 'quantity');
    const price = value(row, 'price');
    if (!NUMBER.test(quantity) || Number(quantity) <= 0) {
      unresolved.push(`${row.sheet} 第 ${row.row} 行数量必须是大于零的数值`);
      continue;
    }
    if (price && !NUMBER.test(price)) {
      unresolved.push(`${row.sheet} 第 ${row.row} 行价格必须是非负数值`);
      continue;
    }
    lines.push({
      line_id: binding.line_id,
      sheet: row.sheet,
      row: row.row,
      model: value(row, 'model'),
      name: value(row, 'name'),
      description: value(row, 'description'),
      quantity,
      unit: value(row, 'unit'),
      brand: value(row, 'brand'),
      price: price || null,
      note: value(row, 'note'),
      section: value(row, 'section'),
      kind: 'hardware',
      variant_id: binding.variant_id,
      source_id: binding.source_id,
      ...(binding.device_id ? { device_id: binding.device_id } : {}),
    });
  }
  return { lines, unresolved };
}
