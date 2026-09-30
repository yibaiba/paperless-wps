export interface RequestAttempt {
  signal: AbortSignal;
  isCurrent(): boolean;
}

export class LatestRequest {
  private sequence = 0;
  private controller?: AbortController;

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
    this.controller?.abort();
    this.controller = undefined;
  }
}
