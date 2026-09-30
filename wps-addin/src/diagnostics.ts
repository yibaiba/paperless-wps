import type { DiagnosticEventInput, DiagnosticEventPayload } from './types';

export const DIAGNOSTIC_OUTBOX_KEY = 'presales_diagnostic_outbox';
export const DIAGNOSTIC_SESSION_KEY = 'presales_diagnostic_session_id';
const PLUGIN_VERSION = '0.1.0';
const EVENT_TYPES = new Set([
  'inline_open', 'focus_lost', 'query_start', 'query_success', 'query_error', 'no_match',
  'tab_register', 'tab_restore', 'tab_accept', 'tab_expand', 'accept_success', 'accept_error',
]);
const EVENT_KEYS = new Set([
  'event_id', 'installation_id', 'session_id', 'occurred_at', 'plugin_version', 'host_os',
  'host_version', 'event_type', 'completion_phase', 'duration_ms', 'candidate_count',
  'completion_ready', 'outcome', 'error_code', 'template_profile_id',
  'template_profile_revision',
]);

interface DiagnosticRecorderOptions {
  get: (key: string) => string | null;
  set: (key: string, value: string) => void;
  installationId: () => string;
  hostOs: () => string;
  hostVersion: () => string;
  identifier?: () => string;
  now?: () => string;
}

export class DiagnosticRecorder {
  private readonly options: DiagnosticRecorderOptions;

  constructor(options: DiagnosticRecorderOptions) { this.options = options; }

  record(input: DiagnosticEventInput) {
    const event: DiagnosticEventPayload = {
      event_id: this.identifier(),
      installation_id: this.options.installationId(),
      session_id: this.sessionId(),
      occurred_at: (this.options.now ?? (() => new Date().toISOString()))(),
      plugin_version: PLUGIN_VERSION,
      host_os: this.options.hostOs() || 'unknown',
      host_version: this.options.hostVersion() || 'unknown',
      ...input,
    };
    const current = parseDiagnosticOutbox(this.options.get(DIAGNOSTIC_OUTBOX_KEY));
    this.options.set(DIAGNOSTIC_OUTBOX_KEY, JSON.stringify([...current, event]));
    return event;
  }

  pending() { return parseDiagnosticOutbox(this.options.get(DIAGNOSTIC_OUTBOX_KEY)); }

  remove(eventIds: string[]) {
    const removed = new Set(eventIds);
    const remaining = this.pending().filter((event) => !removed.has(event.event_id));
    this.options.set(DIAGNOSTIC_OUTBOX_KEY, JSON.stringify(remaining));
  }

  private sessionId() {
    const current = this.options.get(DIAGNOSTIC_SESSION_KEY);
    if (current) return current;
    const created = this.identifier();
    this.options.set(DIAGNOSTIC_SESSION_KEY, created);
    return created;
  }

  private identifier() { return (this.options.identifier ?? (() => crypto.randomUUID()))(); }
}

export function parseDiagnosticOutbox(raw: string | null): DiagnosticEventPayload[] {
  if (!raw) return [];
  let parsed: unknown;
  try { parsed = JSON.parse(raw); }
  catch { throw new Error('WPS 诊断队列损坏，请联系管理员'); }
  if (!Array.isArray(parsed) || !parsed.every(isDiagnosticEvent)) {
    throw new Error('WPS 诊断队列格式无效，请联系管理员');
  }
  return parsed;
}

function isDiagnosticEvent(value: unknown): value is DiagnosticEventPayload {
  if (!value || typeof value !== 'object') return false;
  const event = value as Record<string, unknown>;
  const required = [
    'event_id', 'installation_id', 'session_id', 'occurred_at', 'plugin_version',
    'host_os', 'host_version', 'event_type',
  ];
  if (Object.keys(event).some((key) => !EVENT_KEYS.has(key))) return false;
  if (!required.every((key) => typeof event[key] === 'string')) return false;
  if (!EVENT_TYPES.has(event.event_type as string)) return false;
  const templateId = event.template_profile_id;
  const templateRevision = event.template_profile_revision;
  if (Boolean(templateId) !== Boolean(templateRevision)) return false;
  return optionalNumber(event.duration_ms)
    && optionalNumber(event.candidate_count)
    && optionalBoolean(event.completion_ready)
    && optionalString(event.completion_phase)
    && optionalString(event.outcome)
    && optionalString(event.error_code)
    && optionalString(templateId)
    && (templateRevision === undefined || Number.isInteger(templateRevision));
}

function optionalString(value: unknown) { return value === undefined || typeof value === 'string'; }
function optionalNumber(value: unknown) { return value === undefined || Number.isInteger(value); }
function optionalBoolean(value: unknown) { return value === undefined || typeof value === 'boolean'; }
