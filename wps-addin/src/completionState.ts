import { ghostCompletion, type GhostField } from './inlineCompletion.ts';
import { nextCandidateIndex } from './inlineNavigation.ts';
import { SUGGESTION_DEBOUNCE_MS } from './constants.ts';
import type { Candidate } from './types';

export interface CompletionSelection {
  expanded: boolean;
  explicit: boolean;
  index: number;
}

export type CompletionCommand = 'accept' | 'expand' | 'native-tab' | 'none';
export type CompletionKey = 'ArrowDown' | 'ArrowUp' | 'Escape' | 'Enter' | 'Tab';
export type CompletionPhase =
  | 'typing' | 'loading' | 'ghost' | 'ambiguous' | 'list' | 'no-match' | 'error';

export const EMPTY_SELECTION: CompletionSelection = {
  expanded: false,
  explicit: false,
  index: 0,
};

const COMPLETION_KEYS = new Set<CompletionKey>([
  'ArrowDown', 'ArrowUp', 'Escape', 'Enter', 'Tab',
]);

export function completionKey(key: string, composing: boolean): CompletionKey | null {
  if (composing || !COMPLETION_KEYS.has(key as CompletionKey)) return null;
  return key as CompletionKey;
}

export function suggestionDelay(query: string) {
  return query.trim() ? SUGGESTION_DEBOUNCE_MS : 0;
}

function logicalProduct(candidate: Candidate) {
  return `${candidate.model.trim().toLocaleLowerCase()}\u0000${candidate.name.trim().toLocaleLowerCase()}`;
}

export function candidateIsAmbiguous(candidates: Candidate[], index = 0, query = '') {
  const selected = candidates[index];
  if (!selected) return false;
  const key = logicalProduct(selected);
  if (!selected.completion_ready
    && candidates.filter((candidate) => logicalProduct(candidate) === key).length > 1) return true;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const exactField = (['model', 'name'] as const).find(
    (field) => selected[field].trim().toLocaleLowerCase() === normalizedQuery,
  );
  if (!exactField) return false;
  const value = selected[exactField].trim().toLocaleLowerCase();
  const exactCandidates = candidates.filter(
    (candidate) => candidate[exactField].trim().toLocaleLowerCase() === value,
  );
  const exactProducts = new Set(exactCandidates.map(logicalProduct));
  return exactProducts.size > 1 || (!selected.completion_ready && exactCandidates.length > 1);
}

export function selectionForCandidates(
  query: string,
  candidates: Candidate[],
  preferredField: GhostField = 'name',
): CompletionSelection {
  const hasGhost = Boolean(ghostCompletion(query, candidates[0], preferredField));
  return {
    expanded: candidateIsAmbiguous(candidates, 0, query) || (candidates.length > 0 && !hasGhost),
    explicit: false,
    index: 0,
  };
}

export function navigateCandidates(
  selection: CompletionSelection,
  count: number,
  direction: 1 | -1,
): CompletionSelection {
  return {
    expanded: true,
    explicit: count > 0,
    index: nextCandidateIndex(selection.index, count, direction),
  };
}

export function completionCommand(options: {
  key: 'Tab' | 'Enter';
  candidates: Candidate[];
  selection: CompletionSelection;
  hasGhost: boolean;
  query?: string;
}): CompletionCommand {
  if (options.candidates.length === 0) {
    return options.key === 'Tab' ? 'native-tab' : 'none';
  }
  const needsChoice = candidateIsAmbiguous(
    options.candidates, options.selection.index, options.query,
  )
    || !options.hasGhost;
  if (needsChoice && !options.selection.explicit) {
    return options.key === 'Enter' && options.selection.expanded ? 'accept' : 'expand';
  }
  return 'accept';
}

export function completionPhase(options: {
  busy: boolean;
  error: string;
  candidates: Candidate[];
  selection: CompletionSelection;
  hasGhost: boolean;
  query?: string;
}): CompletionPhase {
  if (options.error) return 'error';
  if (options.busy) return 'loading';
  if (options.candidates.length === 0) return 'no-match';
  if (candidateIsAmbiguous(
    options.candidates, options.selection.index, options.query,
  )) return 'ambiguous';
  if (options.selection.expanded) return 'list';
  return options.hasGhost ? 'ghost' : 'typing';
}
