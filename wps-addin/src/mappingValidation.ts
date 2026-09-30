import type { ManagedField, TemplateField } from './types';

export function validateMapping(
  mapping: Partial<Record<TemplateField, number>>,
  managed: ManagedField[],
) {
  if (!mapping.quantity) throw new Error('请映射数量列');
  if (!mapping.model && !mapping.name) throw new Error('请至少映射产品型号或名称');
  if (!managed.includes('model') && !managed.includes('name')) {
    throw new Error('产品型号或名称至少有一项须由插件填写');
  }
  const columns = Object.values(mapping).filter((value): value is number => Boolean(value));
  if (new Set(columns).size !== columns.length) throw new Error('一个工作表列不能映射到多个字段');
}

export function validateMappedHeaders(
  mapping: Partial<Record<TemplateField, number>>,
  headers: string[],
) {
  for (const column of Object.values(mapping)) {
    if (!column || headers[column - 1]?.trim()) continue;
    throw new Error(`映射的第 ${column} 列没有表头，请检查表头行`);
  }
}
