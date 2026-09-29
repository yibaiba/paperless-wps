import type { Variant, Deployment, Configuration } from '../../types';
import type { EditOperation } from '../sheet/model';

export const fields = [
  ['name', '名称'], ['model', '型号'], ['description', '产品说明'], ['quantity', '采购数量'],
  ['unit', '单位'], ['price', '单价'], ['note', '备注'], ['section', '分区'],
] as const;
export type Field = typeof fields[number][0];
export type Mapping = Partial<Record<Field, number>>;
export interface ImportRow {
  mergedNoteRange?: string;
  systemId?: string; requirementId?: string; roleName?: string; existingDeviceId?: string;
  raw: string[]; id: string; sourceRow: number; include: boolean; choice: string; kind: Deployment['kind'] | '';
  name: string; model: string; description: string; quantity: string;
  unit: string; price: string; note: string; section: string;
}
export interface Choice { key: string; variantId: string; sourceId: string; name: string; model: string; label: string; specification: string; unit: string }
const aliases: Record<Field, string[]> = {
  name: ['名称', '产品名称', '设备名称'], model: ['型号', '产品型号', '设备型号'],
  description: ['产品说明', '说明', '规格', '技术参数', '规格参数'],
  quantity: ['数量', '采购数量', '本次采购数量'], unit: ['单位'], price: ['单价', '报价单价'],
  note: ['备注', '备注说明'], section: ['分区', '系统', '系统名称', '报价分区'],
};
export function detectHeader(rows: string[][]) {
  const index = rows.findIndex((row) => row.some((v) => aliases.model.includes(v.trim())) && row.some((v) => aliases.quantity.includes(v.trim())));
  return index;
}
export function detectMapping(header: string[]): Mapping {
  return Object.fromEntries(fields.flatMap(([key]) => {
    const index = header.findIndex((v) => aliases[key].includes(v.trim()));
    return index >= 0 ? [[key, index]] : [];
  }));
}
export function mappedRows(matrix: string[][], header: number, mapping: Mapping): ImportRow[] {
  let inferredSection = '';
  return matrix.slice(header + 1).map((values, index) => {
    const get = (key: Field) => mapping[key] === undefined ? '' : values[mapping[key]!] ?? '';
    const model = get('model');
    const filled = values.filter((value) => value.trim());
    if (!model.trim() && filled.length === 1 && !/^\d+(?:\.\d+)?$/.test(filled[0])) inferredSection = filled[0];
    return { raw: [...values], id: `row-${header + index + 2}`, sourceRow: header + index + 2,
      include: !!model.trim() && !aliases.model.includes(model.trim()), choice: '', kind: '',
      name: get('name'), model, description: get('description'), quantity: get('quantity'),
      unit: get('unit'), price: get('price'), note: get('note'), section: mapping.section === undefined ? inferredSection : get('section') };
  });
}
export function catalogChoices(variants: Variant[]): Choice[] {
  return variants.flatMap((variant) => (variant.source_details ?? []).map((source) => ({
    key: JSON.stringify([variant.id, source.id]), variantId: variant.id, sourceId: source.id,
    name: variant.product.name, model: variant.product.model, specification: source.specification ?? '', unit: source.unit ?? '',
    label: `${variant.product.model} · ${variant.product.name} · ${variant.name} · ${source.sheet} 第${source.row}行 · ${variant.status === 'confirmed' ? '已确认' : '草稿'}`,
  })));
}
export function matchingChoices(row: ImportRow, choices: Choice[]) { return choices.filter((c) => c.model.trim() === row.model.trim()); }
function decimal(value: string, positive: boolean, label: string) {
  const text = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(text) || (positive && !/[1-9]/.test(text))) throw new Error(`${label}：请输入${positive ? '大于零' : '非负'}的数值，公式请先转换为值。`);
  return text;
}
export function importOperations(rows: ImportRow[], options: { choices: Choice[]; evidence: string; newId: () => string; configuration?: Configuration }): EditOperation[] {
  if (!options.evidence.trim()) throw new Error('请填写清单来源和价格采用依据。');
  const selected = rows.filter((row) => row.include);
  if (!selected.length) throw new Error('请选择需要导入的明细行。');
  const assigned = new Set<string>();
  return selected.flatMap((row): EditOperation[] => {
    const existing = options.configuration?.devices.find((d) => d.id === row.existingDeviceId);
    if (row.existingDeviceId && !existing) throw new Error(`第 ${row.sourceRow} 行：已有设备不存在。`);
    if (existing) return assignmentOperations(row, existing.id, { ...options, assigned });
    const choice = options.choices.find((c) => c.key === row.choice);
    if (!choice) throw new Error(`第 ${row.sourceRow} 行：请确认具体产品配置和资料来源。`);
    if (!row.kind) throw new Error(`第 ${row.sourceRow} 行：请选择硬件、软件、授权或配件类型。`);
    if (row.unit.trim() && choice.unit.trim() && row.unit.trim() !== choice.unit.trim()) throw new Error(`第 ${row.sourceRow} 行：原表单位“${row.unit}”与产品库“${choice.unit}”不同，请核对单位及数量。`);
    const quantity = decimal(row.quantity, true, `第 ${row.sourceRow} 行数量`);
    const price = row.price.trim() ? decimal(row.price, false, `第 ${row.sourceRow} 行单价`) : null;
    const id = options.newId(), evidence = `${options.evidence.trim()}；原表第 ${row.sourceRow} 行${row.mergedNoteRange ? `；备注源合并区域：${row.mergedNoteRange}` : ''}`;
    const operations: EditOperation[] = [
      { action: 'device_put', value: { id, name: choice.name, variant_id: choice.variantId, source_id: choice.sourceId, quantity, kind: row.kind, note: row.note } },
      { action: 'purchase_set', device_id: id, quantity, evidence },
      { action: 'price_set', value: { device_id: id, variant_id: choice.variantId, source_id: choice.sourceId, mode: 'import', unit_price: price, evidence, price_column: '' } },
      { action: 'section_set', device_id: id, section: row.section },
    ];
    if (row.description !== '') operations.push({ action: 'description_set', device_id: id, text: row.description });
    return [...operations, ...assignmentOperations(row, id, { ...options, assigned })];
  });
}

function assignmentOperations(row: ImportRow, deviceId: string, options: { configuration?: Configuration; newId: () => string; assigned: Set<string> }): EditOperation[] {
  if (!row.systemId) {
    if (row.requirementId) throw new Error(`第 ${row.sourceRow} 行：已选角色缺少所属系统，请重新关联。`);
    return [];
  }
  if (!options.configuration?.systems.some((s) => s.id === row.systemId)) throw new Error(`第 ${row.sourceRow} 行：系统不存在。`);
  const requirement = options.configuration.requirements.find((r) => r.id === row.requirementId);
  if (row.requirementId && !requirement) throw new Error(`第 ${row.sourceRow} 行：已选角色不存在，请重新选择。`);
  if (requirement) {
    if (requirement.system_id !== row.systemId || options.assigned.has(requirement.id)) throw new Error(`第 ${row.sourceRow} 行：角色重复分配或不属于该系统。`);
    if (requirement.device_id && requirement.device_id !== deviceId) throw new Error(`第 ${row.sourceRow} 行：角色已关联其他设备，请在选型面板明确换型。`);
    options.assigned.add(requirement.id);
    return [{ action: 'requirement_put', value: { ...requirement, device_id: deviceId } }];
  }
  if (!row.roleName?.trim()) return [];
  return [{ action: 'requirement_put', value: { id: options.newId(), system_id: row.systemId,
    role: row.roleName.trim(), role_id: '', environment: [], resources: [], device_id: deviceId } }];
}
