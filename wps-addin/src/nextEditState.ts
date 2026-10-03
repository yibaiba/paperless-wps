import type { EditDecision, NextEditSuggestion, NextEditTarget } from './businessTypes';
import type { ActiveCell } from './types';

export function nextEditAction(options: {
  suggestion?: NextEditSuggestion; cell: ActiveCell; ready: boolean;
  composing: boolean; explicit: boolean; count: number;
  query?: string;
  primarySuggestionId?: string | null; decision?: EditDecision; target?: NextEditTarget | null;
}): 'native' | 'expand' | 'locate' | 'preview' | 'apply' {
  const { suggestion, cell, ready, composing, explicit, count } = options;
  if (!ready || composing || !suggestion) return 'native';
  if (!explicit && options.decision?.status === 'choice_required') return 'expand';
  const primary = options.primarySuggestionId && options.primarySuggestionId === suggestion.id;
  if (count > 1 && !explicit && !primary) return 'expand';
  if (!explicit && !visiblePrefix(suggestion, cell.column, options.query ?? '')) return 'expand';
  const target = options.target ?? suggestion.patches[0];
  if (target && (target.sheet !== cell.sheet || target.row !== cell.row
    || (options.target && target.column !== cell.column))) return 'locate';
  if (suggestion.acceptance !== 'inline' || !suggestion.applicable) return 'preview';
  return 'apply';
}

export function visiblePrefix(suggestion: NextEditSuggestion, column: number, query: string) {
  const text = nextEditText(suggestion, column);
  return Boolean(text) && text.toLocaleLowerCase().startsWith(query.toLocaleLowerCase());
}

export function nextEditText(suggestion: NextEditSuggestion | undefined, column: number) {
  return suggestion?.patches.find((p) => p.column === column)?.after
    ?? suggestion?.line_bindings[0]?.confirmed_values?.name ?? suggestion?.label ?? '';
}
