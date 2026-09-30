import type {
  BindingState, Candidate, CatalogScopePreview, ProjectSummary, SuggestionFeedbackPayload,
  SyncPreviewResult, TemplateProfile, WorkbookLine,
} from './types';

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

export class WpsApi {
  constructor(private readonly token: () => string | null) {}

  async exchange(code: string) {
    return this.request<{ access_token: string; actor: string }>('/pairings/exchange', {
      method: 'POST', body: JSON.stringify({ code }),
    }, false);
  }

  templates() { return this.request<TemplateProfile[]>('/template-profiles'); }

  template(id: string, revision: number) {
    return this.request<TemplateProfile>(`/template-profiles/${id}?revision=${revision}`);
  }

  saveTemplate(value: Record<string, unknown>) {
    return this.request<TemplateProfile>('/template-profiles', {
      method: 'POST', body: JSON.stringify(value),
    });
  }

  previewSourceScopes(rows: Array<{ model: string; name: string }>) {
    return this.request<{ items: CatalogScopePreview[]; total_rows: number }>(
      '/template-profiles/source-scope-preview', {
        method: 'POST', body: JSON.stringify({ rows }),
      },
    );
  }

  suggestions(value: Record<string, unknown>, signal?: AbortSignal) {
    return this.request<{ items: Candidate[] }>('/suggestions', {
      method: 'POST', body: JSON.stringify(value), signal,
    });
  }

  suggestionFeedback(value: SuggestionFeedbackPayload) {
    return this.request<{ id: string; operation_id: string; status: string }>(
      '/suggestion-feedback', { method: 'POST', body: JSON.stringify(value), keepalive: true },
    );
  }

  projects(query = '') {
    return this.request<{ items: ProjectSummary[] }>(`/projects?query=${encodeURIComponent(query)}`);
  }

  bind(value: Record<string, unknown>) {
    return this.request<BindingState>('/bindings', {
      method: 'POST', body: JSON.stringify(value),
    });
  }

  binding(id: string) { return this.request<BindingState>(`/bindings/${id}`); }

  preview(value: Record<string, unknown>) {
    return this.request<SyncPreviewResult>('/sync/preview', {
      method: 'POST', body: JSON.stringify(value),
    });
  }

  commit(value: Record<string, unknown>) {
    return this.request<BindingState & { status: string; web_url?: string }>(
      '/sync/commit', { method: 'POST', body: JSON.stringify(value) },
    );
  }

  private async request<T>(path: string, options: RequestInit = {}, authenticated = true): Promise<T> {
    const token = this.token();
    const response = await fetch(`${API_BASE}/api/wps${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(authenticated && token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      throw new ApiError(response.status, detail);
    }
    return response.json() as Promise<T>;
  }
}
