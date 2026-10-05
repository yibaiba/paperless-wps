import type { DiagnosticEventInput, DiagnosticEventPayload } from './types';
import type { DiagnosticEventStore } from './diagnosticStore';

export const DIAGNOSTIC_OUTBOX_KEY = 'presales_diagnostic_outbox';
export const DIAGNOSTIC_SESSION_KEY = 'presales_diagnostic_session_id';
const PLUGIN_VERSION = '0.1.1';
const EVENT_TYPES = new Set([
  'inline_open', 'focus_lost', 'query_start', 'query_success', 'query_error', 'no_match',
  'tab_register', 'tab_restore', 'tab_accept', 'tab_expand', 'accept_success', 'accept_error',
  'completion_shown', 'completion_accepted', 'completion_undone', 'completion_replaced', 'completion_retained',
  'phase_timing',
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
  remove: (key: string) => void;
  store: DiagnosticEventStore;
  installationId: () => string;
  hostOs: () => string;
  hostVersion: () => string;
  identifier?: () => string;
  now?: () => string;
}

export class DiagnosticRecorder {
  private readonly options: DiagnosticRecorderOptions;
  private ready?: Promise<void>;
  private identity?: Pick<DiagnosticEventPayload, 'installation_id' | 'session_id' | 'host_os' | 'host_version'>;

  constructor(options: DiagnosticRecorderOptions) { this.options = options; }

  async record(input: DiagnosticEventInput) {
    const eventId = input.event_id ?? this.identifier();
    this.identity ??= { installation_id: this.options.installationId(), session_id: this.sessionId(),
      host_os: this.options.hostOs() || 'unknown', host_version: this.options.hostVersion() || 'unknown' };
    const event: DiagnosticEventPayload = {
      ...this.identity,
      occurred_at: (this.options.now ?? (() => new Date().toISOString()))(),
      plugin_version: PLUGIN_VERSION,
      ...input,
      event_id: eventId,
    };
    if (!isDiagnosticEvent(event)) throw new Error('WPS 诊断事件格式无效；未保存或上传');
    await this.initialize();
    await this.options.store.put([event]);
    return event;
  }

  async pending() {
    await this.initialize();
    // An older window may have appended while migration was awaiting IDB.
    // Recheck on upload, never serialize the legacy outbox on every keypress.
    await this.migrateLegacy();
    return parseDiagnosticOutbox(JSON.stringify(await this.options.store.list()));
  }

  async remove(eventIds: string[]) {
    await this.initialize();
    await this.options.store.remove(eventIds);
  }

  private initialize() {
    return this.ready ??= this.migrateLegacy().catch((error) => { this.ready = undefined; throw error; });
  }

  private async migrateLegacy() {
    const raw = this.options.get(DIAGNOSTIC_OUTBOX_KEY);
    if (!raw) return;
    const events = parseDiagnosticOutbox(raw);
    await this.options.store.put(events);
    const stored = await this.options.store.list({ eventIds: events.map((event) => event.event_id) });
    const byId = new Map(stored.map((event) => [event.event_id, JSON.stringify(event)]));
    if (!events.every((event) => byId.get(event.event_id) === JSON.stringify(event))) {
      throw new Error('WPS 诊断旧队列迁移核对失败；旧记录仍保留');
    }
    if (this.options.get(DIAGNOSTIC_OUTBOX_KEY) === raw) this.options.remove(DIAGNOSTIC_OUTBOX_KEY);
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
