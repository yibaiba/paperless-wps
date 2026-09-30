import type {
  Candidate, InlineEditorContext, SuggestionFeedbackPayload, WorkbookMetadata,
} from './types';
import type { suggestionContext } from './suggestionContext';

const PREVIOUS_CONTEXT_LIMIT = 3;
const NEXT_CONTEXT_LIMIT = 1;

interface FeedbackOptions {
  operationId: string;
  context: InlineEditorContext;
  metadata: WorkbookMetadata;
  productContext: ReturnType<typeof suggestionContext>;
  query: string;
  candidates: Candidate[];
  chosen: Candidate;
}

export function completionFeedbackPayload(
  options: FeedbackOptions,
): SuggestionFeedbackPayload | null {
  const previousVariantId = options.productContext.previous_variant_ids[0];
  if (!previousVariantId) return null;
  return {
    operation_id: options.operationId,
    workbook_instance_id: options.metadata.workbook_instance_id,
    template_profile_id: options.context.profile.id,
    template_profile_revision: options.context.profile.revision,
    sheet: options.context.cell.sheet,
    section: options.productContext.section,
    previous_variant_id: previousVariantId,
    context_previous_variant_ids: options.productContext.previous_variant_ids.slice(
      0, PREVIOUS_CONTEXT_LIMIT,
    ),
    context_next_variant_ids: options.productContext.next_variant_ids.slice(
      0, NEXT_CONTEXT_LIMIT,
    ),
    suggested_variant_id: options.candidates[0]?.variant_id,
    chosen_variant_id: options.chosen.variant_id,
    chosen_source_id: options.chosen.source_id,
    query_kind: options.query.trim() ? 'typed' : 'contextual',
  };
}
