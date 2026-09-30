export function nextCandidateIndex(current: number, count: number, direction: 1 | -1) {
  if (count === 0) return 0;
  return (current + direction + count) % count;
}
