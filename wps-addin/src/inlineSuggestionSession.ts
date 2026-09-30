import type { WpsApi } from './api';
import { CompletionPrefetch, completionPrefetchKey } from './completionPrefetch';
import type { HostAdapter } from './host';
import { suggestionContext } from './suggestionContext';
import type {
  Candidate, InlineEditorContext, SheetRow, WorkbookMetadata,
} from './types';

export const INLINE_CANDIDATE_LIMIT = 6;

export type InlineWorkbookContext = {
  metadata: WorkbookMetadata;
  row: SheetRow;
  product: ReturnType<typeof suggestionContext>;
};

export type InlineWorkbookContextResult =
  | { value: InlineWorkbookContext }
  | { error: string };

export function readInlineWorkbookContext(
  host: HostAdapter,
  context: InlineEditorContext,
): InlineWorkbookContextResult {
  try {
    const metadata = host.readMetadata();
    const row = host.readRow(context.profile, context.cell.row);
    const inheritedSection = inheritedSectionFor(host, context, row, context.cell.row);
    return {
      value: {
        metadata,
        row,
        product: suggestionContext({
          cell: context.cell, row, metadata, inheritedSection,
        }),
      },
    };
  } catch (reason) {
    return { error: reason instanceof Error ? reason.message : String(reason) };
  }
}

export function inlineContextKey(context: InlineEditorContext, metadata: WorkbookMetadata) {
  return completionPrefetchKey({
    workbookInstanceId: metadata.workbook_instance_id,
    profileId: context.profile.id,
    profileRevision: context.profile.revision,
    sheet: context.cell.sheet,
    row: context.cell.row,
    column: context.cell.column,
  });
}

export function startNextRowPrefetch(options: {
  api: WpsApi;
  host: HostAdapter;
  context: InlineEditorContext;
  metadata: WorkbookMetadata;
  prefetch: CompletionPrefetch<Candidate[]>;
}) {
  const { api, host, context, metadata, prefetch } = options;
  const inputField = Object.entries(context.profile.field_columns).find(
    ([, column]) => column === context.cell.column,
  )?.[0] as 'model' | 'name' | 'description' | undefined;
  if (!inputField) return;
  const nextRowNumber = context.cell.row + 1;
  const row = host.readRow(context.profile, nextRowNumber);
  if (row.values[inputField]?.trim()) return;
  if (row.formula_fields.includes(inputField) || row.merged_fields.includes(inputField)) return;
  const inheritedSection = inheritedSectionFor(host, context, row, nextRowNumber);
  const cell = { ...context.cell, row: nextRowNumber, value: '', formula: '', merged: false };
  const nextContext = { ...context, cell };
  const product = suggestionContext({ cell, row, metadata, inheritedSection });
  prefetch.start(inlineContextKey(nextContext, metadata), async () => {
    const result = await api.suggestions({
      query: '',
      workbook_instance_id: metadata.workbook_instance_id,
      template_profile_id: context.profile.id,
      template_profile_revision: context.profile.revision,
      draft_id: metadata.binding?.draft_id,
      current_row: row.values,
      context: product,
    });
    return result.items.slice(0, INLINE_CANDIDATE_LIMIT);
  });
}

function inheritedSectionFor(
  host: HostAdapter,
  context: InlineEditorContext,
  row: SheetRow,
  rowNumber: number,
) {
  if (row.values.section?.trim()) return '';
  return host.readInheritedField(context.profile, { row: rowNumber, field: 'section' });
}
