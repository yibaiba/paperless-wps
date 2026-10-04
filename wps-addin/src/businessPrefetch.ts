import type { BindingState, InlineEditorContext } from './types';
import type { CompletionPreviewResult } from './businessTypes';

export function businessPrefetchKey(options: {
  context: InlineEditorContext; binding: BindingState; localRevision: number;
  versions: Record<string, string | null>;
}) {
  const { context, binding, localRevision, versions } = options;
  return JSON.stringify([context.workbook_key, context.profile.id, context.profile.revision,
    context.cell.sheet, context.cell.row, context.cell.column, binding.binding_id,
    binding.binding_revision, binding.draft_revision, binding.base_revision, localRevision,
    Object.entries(versions).sort(([a], [b]) => a.localeCompare(b))]);
}

// Prefetch the next business decision; its target may be an earlier row or no cell at all.
export class BusinessPrefetch {
  private pending?: { key: string; controller: AbortController;
    result: Promise<{ value: CompletionPreviewResult } | { error: unknown }> };
  start(key: string, load: (signal: AbortSignal) => Promise<CompletionPreviewResult>) {
    this.clear();
    const controller = new AbortController();
    this.pending = { key, controller, result: load(controller.signal).then(
      (value) => ({ value }), (error) => ({ error }),
    ) };
  }
  take(key: string, signal?: AbortSignal) {
    if (this.pending?.key !== key) { this.clear(); return undefined; }
    const pending = this.pending;
    this.pending = undefined;
    if (!signal) return pending.result;
    const cancel = () => pending.controller.abort();
    if (signal.aborted) cancel();
    else signal.addEventListener('abort', cancel, { once: true });
    return pending.result.finally(() => signal.removeEventListener('abort', cancel));
  }
  clear() { this.pending?.controller.abort(); this.pending = undefined; }
}
