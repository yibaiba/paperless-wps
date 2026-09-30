export type PrefetchOutcome<T> = { value: T } | { error: Error };

function asError(reason: unknown) {
  return reason instanceof Error ? reason : new Error(String(reason));
}

export class CompletionPrefetch<T> {
  private readonly pending = new Map<string, Promise<PrefetchOutcome<T>>>();

  start(key: string, load: () => Promise<T>) {
    const outcome = load().then<PrefetchOutcome<T>, PrefetchOutcome<T>>(
      (value) => ({ value }),
      (reason) => ({ error: asError(reason) }),
    );
    this.pending.set(key, outcome);
  }

  take(key: string) {
    const outcome = this.pending.get(key);
    this.pending.delete(key);
    return outcome;
  }
}

export function completionPrefetchKey(options: {
  workbookInstanceId: string;
  profileId: string;
  profileRevision: number;
  sheet: string;
  row: number;
  column: number;
}) {
  return [
    options.workbookInstanceId,
    `${options.profileId}@${options.profileRevision}`,
    options.sheet,
    options.row,
    options.column,
  ].join(':');
}
