import type { NextEditSuggestion } from './businessTypes';
import type { ActiveCell } from './types';

export function nextEditAction(options: {
  suggestion?: NextEditSuggestion; cell: ActiveCell; ready: boolean;
  composing: boolean; explicit: boolean; count: number;
}): 'native' | 'expand' | 'locate' | 'preview' | 'apply' {
  const { suggestion, cell, ready, composing, explicit, count } = options;
  if (!ready || composing || !suggestion) return 'native';
  if (count > 1 && !explicit) return 'expand';
  const target = suggestion.patches[0];
  if (target && (target.sheet !== cell.sheet || target.row !== cell.row)) return 'locate';
  if (suggestion.acceptance !== 'inline' || !suggestion.applicable) return 'preview';
  return 'apply';
}

export function nextEditText(suggestion: NextEditSuggestion | undefined, column: number) {
  return suggestion?.patches.find((p) => p.column === column)?.after
    ?? suggestion?.line_bindings[0]?.confirmed_values?.name ?? suggestion?.label ?? '';
}
