import type { ActiveCell, TemplateProfile } from './types';

const INPUT_FIELDS = ['model', 'name', 'description'] as const;

export function isProductInputCell(profile: TemplateProfile, cell: ActiveCell) {
  return cell.sheet === profile.sheet_selector && cell.row > profile.header_row
    && !cell.formula.startsWith('=') && !cell.merged
    && INPUT_FIELDS.some((field) => profile.managed_fields.includes(field)
      && profile.field_columns[field] === cell.column);
}
