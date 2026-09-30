import type { Candidate } from './types';

function logicalProduct(candidate: Candidate) {
  return [candidate.model, candidate.name]
    .map((value) => value.trim().toLocaleLowerCase())
    .join('\0');
}

export function prioritizeInlineCandidates(candidates: Candidate[], limit: number) {
  if (!candidates.length || limit <= 0) return [];
  const topProduct = logicalProduct(candidates[0]);
  const topConfigurations: Candidate[] = [];
  const representatives: Candidate[] = [];
  const repeatedConfigurations: Candidate[] = [];
  const seenProducts = new Set([topProduct]);

  for (const candidate of candidates) {
    const product = logicalProduct(candidate);
    if (product === topProduct) {
      topConfigurations.push(candidate);
    } else if (!seenProducts.has(product)) {
      seenProducts.add(product);
      representatives.push(candidate);
    } else {
      repeatedConfigurations.push(candidate);
    }
  }
  return [...topConfigurations, ...representatives, ...repeatedConfigurations].slice(0, limit);
}
