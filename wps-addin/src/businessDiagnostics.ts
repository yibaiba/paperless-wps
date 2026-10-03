import type { DiagnosticEventInput } from './types';

interface DiagnosticHost {
  recordDiagnostic?(value: DiagnosticEventInput): unknown;
  reportBackgroundError?(message: string): void;
}

export function businessDiagnostic(host: DiagnosticHost, event: DiagnosticEventInput) {
  try { host.recordDiagnostic?.(event); }
  catch (reason) {
    // Diagnostics are outside the write transaction. Failure is surfaced in the task pane.
    host.reportBackgroundError?.(`业务编辑诊断入队失败：${String(reason)}`);
  }
}
