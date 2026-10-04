/** Display merged text once, retaining the first selected cell as the evidence identity. */
export function visibleSegments<T extends { id: string; location: string; text: string; anchor: string }>(segments: T[], query: string): T[] {
  const groups = new Map<string, T>();
  for (const segment of segments) {
    if (segment.text === '') continue;
    const sheet = segment.location.slice(0, segment.location.lastIndexOf('!'));
    const key = `${sheet}!${segment.anchor}`;
    if (!groups.has(key)) groups.set(key, segment);
  }
  const term = query.trim().toLocaleLowerCase();
  return [...groups.values()].filter(s => !term || `${s.location} ${s.anchor} ${s.text}`.toLocaleLowerCase().includes(term));
}
