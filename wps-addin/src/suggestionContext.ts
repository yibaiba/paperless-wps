import type { ActiveCell, SheetRow, WorkbookMetadata } from './types';

const MAX_PREVIOUS_VARIANTS = 8;
const MAX_NEXT_VARIANTS = 3;

interface SuggestionContextInput {
  cell: ActiveCell;
  row: SheetRow;
  metadata: WorkbookMetadata;
  inheritedSection?: string;
}

export function suggestionContext(options: SuggestionContextInput) {
  const { cell, row, metadata } = options;
  const sheetBindings = metadata.line_bindings.filter((item) => item.sheet === cell.sheet);
  const current = sheetBindings.find((item) => item.row === cell.row);
  const previous = [...sheetBindings]
    .filter((item) => item.row < cell.row)
    .sort((left, right) => right.row - left.row)
    .slice(0, MAX_PREVIOUS_VARIANTS)
    .map((item) => ({ variant_id: item.variant_id, source_id: item.source_id }));
  const next = [...sheetBindings]
    .filter((item) => item.row > cell.row)
    .sort((left, right) => left.row - right.row)
    .slice(0, MAX_NEXT_VARIANTS)
    .map((item) => ({ variant_id: item.variant_id, source_id: item.source_id }));
  const section = row.values.section?.trim() || options.inheritedSection?.trim() || '';
  return {
    sheet: cell.sheet,
    section,
    system: section,
    role: '',
    selected_variant_id: current?.variant_id,
    selected_source_id: current?.source_id,
    previous_variant_ids: previous.map((item) => item.variant_id),
    previous_source_ids: previous.map((item) => item.source_id),
    next_variant_ids: next.map((item) => item.variant_id),
    next_source_ids: next.map((item) => item.source_id),
  };
}
