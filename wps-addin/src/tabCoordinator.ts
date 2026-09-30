export const TAB_SESSION_KEY = 'presales_tab_session';

export interface TabSession {
  session_id: string;
  revision: string;
  status: 'ready' | 'processing';
  operation_id?: string;
}

interface TabCoordinatorOptions {
  app: any;
  get: (key: string) => string | null;
  set: (key: string, value: string) => void;
  operationId?: () => string;
}

export class WpsTabCoordinator {
  private readonly options: TabCoordinatorOptions;

  constructor(options: TabCoordinatorOptions) { this.options = options; }

  capabilityIssues() {
    const issues: string[] = [];
    if (typeof this.options.app?.OnKey !== 'function') issues.push('Application.OnKey');
    const storage = this.options.app?.PluginStorage;
    if (typeof storage?.getItem !== 'function' || typeof storage?.setItem !== 'function') {
      issues.push('PluginStorage');
    }
    return issues;
  }

  activate(sessionId: string, revision: string) {
    const current = this.session();
    if (current?.session_id === sessionId && current.revision === revision) return;
    this.write({ session_id: sessionId, revision, status: 'ready' });
    this.options.app.OnKey('{TAB}', 'PresalesTab');
  }

  claim(sessionId: string) {
    const current = this.session();
    if (!current || current.session_id !== sessionId || current.status !== 'ready') return null;
    const operationId = (this.options.operationId ?? (() => crypto.randomUUID()))();
    this.write({ ...current, status: 'processing', operation_id: operationId });
    return operationId;
  }

  restore(sessionId?: string) {
    const current = this.session();
    if (sessionId && current?.session_id !== sessionId) return;
    this.options.set(TAB_SESSION_KEY, '');
    this.options.app?.OnKey?.('{TAB}');
  }

  session() {
    const raw = this.options.get(TAB_SESSION_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw) as TabSession; }
    catch { throw new Error('Tab 补全会话损坏，请重新选择单元格'); }
  }

  private write(value: TabSession) {
    this.options.set(TAB_SESSION_KEY, JSON.stringify(value));
  }
}
