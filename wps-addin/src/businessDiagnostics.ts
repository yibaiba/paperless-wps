import type { DiagnosticEventInput } from './types';

interface DiagnosticHost {
  recordDiagnostic?(value: DiagnosticEventInput): unknown;
  reportBackgroundError?(message: string): void;
}

export function businessDiagnostic(host: DiagnosticHost, event: DiagnosticEventInput) {
  const report = (reason: unknown) => host.reportBackgroundError?.(`业务编辑诊断入队失败：${String(reason)}`);
  try { void Promise.resolve(host.recordDiagnostic?.(event)).catch(report); }
  catch (reason) {
    // Diagnostics are outside the write transaction. Failure is surfaced in the task pane.
    report(reason);
  }
}
