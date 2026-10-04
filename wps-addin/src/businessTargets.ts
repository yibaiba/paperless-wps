import type { BusinessScope } from './businessTypes';
import type { SheetRow, TemplateProfile } from './types';

export function availableProductTarget(options: {
  scope: BusinessScope; activeRow: number; profile: TemplateProfile;
  occupied: ReadonlySet<number>; readRow: (row: number) => SheetRow;
}) {
  const { scope, activeRow, occupied, profile, readRow } = options;
  const fields = new Set([...profile.managed_fields, 'quantity']);
  const distance = Math.max(scope.end_row - activeRow, activeRow - scope.start_row);
  for (let offset = 1; offset <= distance; offset += 1) {
    // Nearest safe row, below first on a tie; edits to existing rows keep their own targets.
    for (const row of [activeRow + offset, activeRow - offset]) {
      if (row < scope.start_row || row > scope.end_row || occupied.has(row)) continue;
      const value = readRow(row);
      if (value.values.model?.trim() || value.values.name?.trim()) continue;
      if ([...value.formula_fields, ...value.merged_fields].some((field) => fields.has(field))) continue;
      return value;
    }
  }
  return undefined;
}
