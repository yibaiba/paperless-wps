import type { CompletionPreviewResult } from './businessTypes';
import type { ActiveCell } from './types';
import { nextEditAction, nextEditText } from './nextEditState.ts';

export function businessCompletionSelection(options: {
  result: CompletionPreviewResult; cell: ActiveCell; query: string;
}) {
  const { result, cell, query } = options;
  const primary = result.items.findIndex((item) => item.id === result.primary_suggestion_id);
  const index = Math.max(0, primary);
  const action = nextEditAction({ suggestion: result.items[index], cell, query,
    ready: true, composing: false, explicit: false, count: result.items.length,
    primarySuggestionId: result.primary_suggestion_id, decision: result.decision,
    target: primary === index ? result.next_target : undefined });
  return { index, expanded: action === 'expand' };
}

export function resolvedBusinessChoice(options: {
  result: CompletionPreviewResult; cell: ActiveCell; query: string;
}) {
  const { result, cell, query } = options;
  const { index } = businessCompletionSelection(options);
  const suggestion = result.items[index];
  const action = nextEditAction({ suggestion, cell, query, ready: true, composing: false,
    explicit: result.items.length === 1, count: result.items.length,
    primarySuggestionId: result.primary_suggestion_id, decision: result.decision,
    target: suggestion?.id === result.primary_suggestion_id ? result.next_target : undefined });
  return { index, action };
}

export function businessCompletionGhost(options: {
  result?: CompletionPreviewResult; index: number; cell: ActiveCell; query: string;
  ready: boolean; explicit: boolean;
}) {
  const { result, index, cell, query, ready, explicit } = options;
  const suggestion = result?.items[index];
  const action = nextEditAction({ suggestion, cell, query, ready, explicit, composing: false,
    count: result?.items.length ?? 0, primarySuggestionId: result?.primary_suggestion_id,
    decision: result?.decision, target: suggestion?.id === result?.primary_suggestion_id ? result?.next_target : undefined });
  if (action !== 'apply') return null;
  const text = nextEditText(suggestion, cell.column);
  if (!text.toLocaleLowerCase().startsWith(query.toLocaleLowerCase())) return null;
  return { prefix: query, suffix: text.slice(query.length) };
}
