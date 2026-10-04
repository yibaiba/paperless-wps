import type { NextEditSuggestion } from './businessTypes';
import type { InlineEditorContext } from './types';

export interface LocatedProductChoice {
  readonly contextKey: string;
  readonly localRevision: number;
  readonly selected_variant_id: string;
  readonly selected_source_id: string;
}

function contextKey(context: InlineEditorContext): string {
  const { workbook_key, binding_id, session_id, nonce, profile, cell } = context;
  return JSON.stringify([workbook_key, binding_id, session_id, nonce, profile.id, profile.revision,
    cell.sheet, cell.row, cell.column, cell.value]);
}

// Keep an explicit choice only at its newly located cell. It is input to a fresh
// server preview, never authority to apply the previous suggestion there.
export function locatedProductChoice(options: {
  context: InlineEditorContext | null; suggestion: NextEditSuggestion;
}): LocatedProductChoice | undefined {
  const { context, suggestion } = options;
  if (!context) return undefined;
  const bindings = suggestion.line_bindings.filter((line) =>
    line.sheet === context.cell.sheet && line.row === context.cell.row);
  if (bindings.length !== 1 || !bindings[0].variant_id || !bindings[0].source_id) return undefined;
  return { contextKey: contextKey(context), localRevision: suggestion.local_revision,
    selected_variant_id: bindings[0].variant_id, selected_source_id: bindings[0].source_id };
}

export function locatedChoiceRequest(options: {
  choice?: LocatedProductChoice; context: InlineEditorContext; localRevision: number; query: string;
}) {
  const { choice, context, localRevision, query } = options;
  if (!choice || query || choice.localRevision !== localRevision || choice.contextKey !== contextKey(context)) return undefined;
  return { selected_variant_id: choice.selected_variant_id, selected_source_id: choice.selected_source_id };
}
