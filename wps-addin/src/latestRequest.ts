export interface RequestAttempt {
  signal: AbortSignal;
  isCurrent(): boolean;
}

export class LatestRequest {
  private sequence = 0;
  private controller?: AbortController;
  private timer?: ReturnType<typeof setTimeout>;

  schedule(delayMs: number, run: (request: RequestAttempt) => void): () => void {
    // Invalidate the old request before debounce, not when the timer fires.
    const request = this.begin();
    this.timer = setTimeout(() => {
      if (!request.isCurrent()) return;
      this.timer = undefined;
      run(request);
    }, delayMs);
    return () => {
      if (request.isCurrent()) this.cancel();
    };
  }

  begin(): RequestAttempt {
    this.cancel();
    const sequence = this.sequence;
    const controller = new AbortController();
    this.controller = controller;
    return {
      signal: controller.signal,
      isCurrent: () => sequence === this.sequence && !controller.signal.aborted,
    };
  }

  cancel() {
    this.sequence += 1;
    clearTimeout(this.timer);
    this.timer = undefined;
    this.controller?.abort();
    this.controller = undefined;
  }
}
