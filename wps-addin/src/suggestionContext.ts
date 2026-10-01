import type { ActiveCell, SheetRow, WorkbookMetadata } from './types';
import { bindingForRow } from './workbook.ts';

const MAX_PREVIOUS_VARIANTS = 8;
const MAX_NEXT_VARIANTS = 3;
const MAX_SHEET_VARIANTS = 200;

interface SuggestionContextInput {
  cell: ActiveCell;
  row: SheetRow;
  metadata: WorkbookMetadata;
  inheritedSection?: string;
}

function bindingsForSection(
  bindings: WorkbookMetadata['line_bindings'],
  section: string,
) {
  const sectionsKnown = bindings.every((item) => item.section !== undefined);
  if (!sectionsKnown) return bindings;
  return bindings.filter((item) => item.section?.trim() === section);
}

export function suggestionContext(options: SuggestionContextInput) {
  const { cell, row, metadata } = options;
  const sheetBindings = metadata.line_bindings.filter((item) => item.sheet === cell.sheet);
  const section = row.values.section?.trim() || options.inheritedSection?.trim() || '';
  const current = bindingForRow(row, sheetBindings);
  const exact = sheetBindings.find((item) => item.row === cell.row);
  const changedIdentity = Boolean(row.values.model?.trim() || row.values.name?.trim());
  const stableBindings = exact?.anchor_fingerprint && exact !== current && changedIdentity
    ? sheetBindings.filter((item) => item !== exact)
    : sheetBindings;
  const contextBindings = bindingsForSection(stableBindings, section);
  const sequenceBindings = contextBindings.filter((item) => item !== current);
  const previous = [...sequenceBindings]
    .filter((item) => item.row < cell.row)
    .sort((left, right) => right.row - left.row)
    .slice(0, MAX_PREVIOUS_VARIANTS)
    .map((item) => ({ variant_id: item.variant_id, source_id: item.source_id }));
  const next = [...sequenceBindings]
    .filter((item) => item.row > cell.row)
    .sort((left, right) => left.row - right.row)
    .slice(0, MAX_NEXT_VARIANTS)
    .map((item) => ({ variant_id: item.variant_id, source_id: item.source_id }));
  const sheetContext = [...contextBindings]
    .sort((left, right) => {
      const distance = Math.abs(left.row - cell.row) - Math.abs(right.row - cell.row);
      return distance || left.row - right.row;
    })
    .slice(0, MAX_SHEET_VARIANTS);
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
    sheet_variant_ids: sheetContext.map((item) => item.variant_id),
    sheet_source_ids: sheetContext.map((item) => item.source_id),
  };
}
