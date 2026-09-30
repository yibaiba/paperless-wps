import type { Candidate } from './types';

export interface GhostCompletion {
  prefix: string;
  suffix: string;
}

export type GhostField = 'model' | 'name';

export function ghostCompletion(
  query: string,
  candidate?: Candidate,
  preferredField: GhostField = 'name',
): GhostCompletion | null {
  if (!candidate || !candidate.completion_ready
    || candidate.confidence !== 'high' || query !== query.trim()) return null;
  const alternateField = preferredField === 'name' ? 'model' : 'name';
  const fields = [candidate[preferredField], candidate[alternateField]];
  if (!query) {
    const value = fields.find(Boolean) ?? '';
    return value ? { prefix: '', suffix: value } : null;
  }
  const normalizedQuery = query.toLocaleLowerCase();
  const value = fields.find((item) =>
    item.toLocaleLowerCase().startsWith(normalizedQuery));
  if (!value) return null;
  return { prefix: value.slice(0, query.length), suffix: value.slice(query.length) };
}
