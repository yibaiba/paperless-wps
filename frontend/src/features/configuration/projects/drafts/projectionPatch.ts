export type ProjectionPatch = { value: unknown } | { fields: Record<string, ProjectionPatch>; removed: string[] } | { items: Record<string, ProjectionPatch>; length: number };
export function applyProjectionPatch(before: unknown, patch: ProjectionPatch | null): unknown {
  if (!patch) return before;
  if ('value' in patch) return patch.value;
  if ('items' in patch) {
    const result = Array.isArray(before) ? before.slice(0, patch.length) : [];
    for (const [index, change] of Object.entries(patch.items)) result[Number(index)] = applyProjectionPatch(result[Number(index)], change);
    return result;
  }
  const result = { ...(before as Record<string, unknown> ?? {}) };
  for (const key of patch.removed) delete result[key];
  for (const [key, change] of Object.entries(patch.fields)) Object.defineProperty(result, key, { value: applyProjectionPatch(result[key], change), enumerable: true, configurable: true, writable: true });
  return result;
}
