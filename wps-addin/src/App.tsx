import {
  AppstoreOutlined, LinkOutlined, LoginOutlined, SearchOutlined, TableOutlined,
} from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { WpsApi } from './api';
import { applyCandidate } from './candidateAcceptance';
import { BindingPanel } from './components/BindingPanel';
import { MappingPanel } from './components/MappingPanel';
import { SuggestionPanel } from './components/SuggestionPanel';
import { SyncPanel } from './components/SyncPanel';
import { SUGGESTION_DEBOUNCE_MS } from './constants';
import { WpsHostAdapter } from './host';
import { LatestRequest } from './latestRequest';
import { matchingProfile } from './template';
import { suggestionContext } from './suggestionContext';
import type {
  ActiveCell, BindingState, Candidate, TemplateField, TemplateProfile,
  WorkbookMetadata,
} from './types';

type View = 'account' | 'suggestions' | 'mapping' | 'binding' | 'sync';
const HOST_STATE_POLL_MS = 250;

export function App() {
  const host = useMemo(() => new WpsHostAdapter(), []);
  const [token, setToken] = useState(() => host.token());
  const [actor, setActor] = useState(() => host.account());
  const api = useMemo(() => new WpsApi(() => token), [token]);
  const [metadata, setMetadata] = useState<WorkbookMetadata>(() => host.readMetadata());
  const [profiles, setProfiles] = useState<TemplateProfile[]>([]);
  const [profile, setProfile] = useState<TemplateProfile>();
  const [view, setView] = useState<View>('suggestions');
  const [cell, setCell] = useState<ActiveCell>();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pairing, setPairing] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const requests = useRef(new LatestRequest());
  const attemptedFeedback = useRef(new Set<string>());
  const diagnosticsInFlight = useRef(false);
  const capabilityIssues = useMemo(() => host.inlineCapabilityIssues(), [host]);

  const loadProfiles = useCallback(async () => {
    if (!token) return;
    const values = await api.templates();
    let bound = values.find((item) => item.id === metadata.profile_id
      && item.revision === metadata.profile_revision);
    if (!bound && metadata.profile_id && metadata.profile_revision) {
      bound = await api.template(metadata.profile_id, metadata.profile_revision);
    }
    const all = bound && !values.some((item) => item.id === bound.id
      && item.revision === bound.revision) ? [...values, bound] : values;
    setProfiles(all);
    const matched = bound ?? await matchingProfile(all, (item) =>
      Promise.resolve(host.readHeader(item.sheet_selector, item.header_row)));
    setProfile(matched);
    if (!matched) setView('mapping');
  }, [api, host, metadata.profile_id, metadata.profile_revision, token]);

  useEffect(() => { loadProfiles().catch((reason) => setError(String(reason))); }, [loadProfiles]);

  useEffect(() => {
    const bindingId = metadata.binding?.binding_id;
    if (!token || !bindingId) return;
    api.binding(bindingId).then((binding) => {
      if (binding.binding_revision <= (metadata.binding?.binding_revision ?? 0)) return;
      const lineBindings = binding.line_bindings.map((item) => {
        const local = metadata.line_bindings.find((value) => value.line_id === item.line_id);
        return { ...item, anchor_fingerprint: local?.anchor_fingerprint };
      });
      const next = { ...metadata, binding, line_bindings: lineBindings };
      host.writeMetadata(next);
      setMetadata(next);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [api, host, metadata, token]);

  const queryCell = useCallback((showEditor: boolean) => {
    if (!profile || capabilityIssues.length) return;
    let current: ActiveCell;
    try { current = host.activeCell(); } catch (reason) { setError(String(reason)); return; }
    const suggestionFields: TemplateField[] = ['model', 'name', 'description'];
    const allowed = suggestionFields.some(
      (field) => profile.field_columns[field] === current.column,
    );
    requests.current.cancel();
    clearTimeout(timer.current);
    setCell(allowed && current.sheet === profile.sheet_selector ? current : undefined);
    setCandidates([]);
    if (!allowed || current.sheet !== profile.sheet_selector) {
      if (showEditor) host.hideInlineEditor();
      return;
    }
    if (showEditor) host.showInlineEditor(profile, current);
    const inlineCell = host.inlineContext()?.cell;
    const inlineOwnsQuery = inlineCell?.sheet === current.sheet
      && inlineCell.row === current.row
      && inlineCell.column === current.column;
    if (inlineOwnsQuery) return;
    if (!current.value.trim()) return;
    timer.current = setTimeout(async () => {
      const request = requests.current.begin();
      setBusy(true); setError('');
      try {
        const currentRow = host.readRow(profile, current.row);
        const inheritedSection = currentRow.values.section?.trim() ? '' : host.readInheritedField(
          profile,
          { row: current.row, field: 'section' },
        );
        const productContext = suggestionContext({
          cell: current, row: currentRow, metadata, inheritedSection,
        });
        const result = await api.suggestions({
          query: current.value.trim(),
          workbook_instance_id: metadata.workbook_instance_id,
          template_profile_id: profile.id,
          template_profile_revision: profile.revision,
          draft_id: metadata.binding?.draft_id,
          current_row: currentRow?.values ?? {},
          context: productContext,
        }, request.signal);
        if (request.isCurrent()) setCandidates(result.items);
      } catch (reason) {
        if (request.isCurrent()) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      } finally { if (request.isCurrent()) setBusy(false); }
    }, SUGGESTION_DEBOUNCE_MS);
  }, [api, capabilityIssues, host, metadata, profile]);

  useEffect(() => {
    if (!profile || capabilityIssues.length) return undefined;
    const removeChange = host.onSheetChange(() => queryCell(false));
    const removeSelection = host.onSelectionChange(() => queryCell(true));
    const removeSheetActivate = host.onSheetActivate(() => host.hideInlineEditor());
    const removeWorkbookClose = host.onWorkbookBeforeClose(() => host.hideInlineEditor());
    queryCell(true);
    return () => {
      removeChange(); removeSelection(); removeSheetActivate(); removeWorkbookClose();
      requests.current.cancel(); clearTimeout(timer.current);
      host.hideInlineEditor();
    };
  }, [capabilityIssues, host, profile, queryCell]);

  const accept = useCallback((candidate: Candidate) => {
    if (!profile || !cell) return;
    setCandidates([]);
    try {
      const currentRow = host.readRow(profile, cell.row);
      const section = currentRow.values.section?.trim() || host.readInheritedField(
        profile, { row: cell.row, field: 'section' },
      ).trim();
      setMetadata(applyCandidate({
        host, profile, cell, metadata, candidate, section,
      }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }, [cell, host, metadata, profile]);

  useEffect(() => {
    if (capabilityIssues.length) return undefined;
    let metadataNonce = host.metadataNonce();
    const views: Record<string, View> = {
      connect: 'account', mapping: 'mapping', binding: 'binding', sync: 'sync', open: 'suggestions',
    };
    const poll = window.setInterval(() => {
      const nextNonce = host.metadataNonce();
      if (nextNonce !== metadataNonce) {
        metadataNonce = nextNonce;
        setMetadata(host.readMetadata());
      }
      const backgroundError = host.backgroundError();
      if (backgroundError) {
        setError(backgroundError);
        host.clearBackgroundError();
      }
      const action = host.requestedAction();
      if (!action || !views[action]) return;
      setView(views[action]);
      host.clearRequestedAction();
      if (action === 'open' || action === 'mapping') {
        loadProfiles().catch((reason) => setError(
          reason instanceof Error ? reason.message : String(reason),
        ));
      }
    }, HOST_STATE_POLL_MS);
    return () => window.clearInterval(poll);
  }, [capabilityIssues.length, host, loadProfiles]);

  useEffect(() => {
    if (!token) return undefined;
    const flush = async () => {
      const pending = host.pendingSuggestionFeedback().filter(
        (item) => !attemptedFeedback.current.has(item.operation_id),
      );
      for (const item of pending) {
        attemptedFeedback.current.add(item.operation_id);
        try {
          await api.suggestionFeedback(item);
          host.removeSuggestionFeedback(item.operation_id);
        } catch (reason) {
          const message = reason instanceof Error ? reason.message : String(reason);
          setError(`产品顺序学习失败：${message}`);
        }
      }
    };
    const poll = window.setInterval(() => { void flush(); }, 1000);
    void flush();
    return () => window.clearInterval(poll);
  }, [api, host, token]);

  useEffect(() => {
    if (!token) return undefined;
    const flush = async () => {
      if (diagnosticsInFlight.current) return;
      try {
        const pending = host.pendingDiagnostics().slice(0, 50);
        if (!pending.length) return;
        diagnosticsInFlight.current = true;
        await api.diagnostics(pending);
        host.removeDiagnostics(pending.map((event) => event.event_id));
      } catch (reason) {
        const message = reason instanceof Error ? reason.message : String(reason);
        setError(`WPS 诊断上传失败：${message}`);
      } finally {
        diagnosticsInFlight.current = false;
      }
    };
    const poll = window.setInterval(() => { void flush(); }, 2000);
    void flush();
    return () => window.clearInterval(poll);
  }, [api, host, token]);

  async function connect() {
    setBusy(true); setError('');
    try {
      const result = await api.exchange(pairing);
      host.saveToken(result.access_token);
      host.saveAccount(result.actor);
      setToken(result.access_token);
      setActor(result.actor);
      setPairing('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  function saveProfile(value: TemplateProfile) {
    const next = { ...metadata, profile_id: value.id, profile_revision: value.revision };
    host.writeMetadata(next); setMetadata(next); setProfile(value);
    setProfiles((items) => [...items.filter((item) => item.id !== value.id), value]);
    setView('suggestions');
  }

  function saveBinding(value: BindingState) {
    const productBindings = metadata.line_bindings.map(({ device_id: _, ...item }) => item);
    const next = { ...metadata, binding: value, line_bindings: productBindings };
    host.writeMetadata(next); setMetadata(next); setView('sync');
  }

  function selectProfile(value?: TemplateProfile) {
    const next = {
      ...metadata,
      profile_id: value?.id,
      profile_revision: value?.revision,
    };
    host.writeMetadata(next); setMetadata(next); setProfile(value);
  }

  if (!host.ready()) return <main className="fatal"><h1>售前产品助手</h1><div className="error">请在 WPS 表格中打开工作簿后重试。</div></main>;
  if (capabilityIssues.length) return <main className="fatal"><h1>售前产品助手</h1>
    <div className="error">当前 WPS 版本不支持完整的内联 Tab 补全：
      {capabilityIssues.join('、')}。请使用已通过验证的 WPS 构建。</div>
  </main>;
  if (!token) return <main className="login">
    <div className="brand"><AppstoreOutlined /><div><h1>售前产品助手</h1><p>未连接</p></div></div>
    <label>一次性配对码<input autoFocus value={pairing} onChange={(event) => setPairing(event.target.value)} /></label>
    {error ? <div className="error" role="alert">{error}</div> : null}
    <button className="primary" onClick={connect} disabled={busy || !pairing.trim()}>
      <LoginOutlined />{busy ? '连接中' : '连接账号'}
    </button>
  </main>;

  return <main>
    <header className="app-header">
      <div><h1>售前产品助手</h1><p>{profile?.name ?? '模板未映射'}</p></div>
      <span className={metadata.binding ? 'connected' : 'not-connected'}>
        {metadata.binding ? `项目 v${metadata.binding.base_revision}` : '未绑定'}
      </span>
    </header>
    <nav className="tabs" aria-label="助手功能">
      <Tab icon={<SearchOutlined />} label="联想" active={view === 'suggestions'} onClick={() => setView('suggestions')} />
      <Tab icon={<TableOutlined />} label="模板" active={view === 'mapping'} onClick={() => setView('mapping')} />
      <Tab icon={<LinkOutlined />} label="项目" active={view === 'binding'} onClick={() => setView('binding')} />
      <Tab icon={<AppstoreOutlined />} label="同步" active={view === 'sync'} onClick={() => setView('sync')} />
    </nav>
    {view === 'account' ? <section className="panel-section" aria-labelledby="account-title">
      <div className="section-heading">
        <div><h2 id="account-title">连接账号</h2><p>当前加载项身份</p></div><LoginOutlined />
      </div>
      <div className="account-status"><span>已连接</span><strong>{actor ?? '个人账号'}</strong></div>
    </section> : null}
    {view === 'suggestions' && profile ? <SuggestionPanel cell={cell} candidates={candidates} busy={busy} error={error} onAccept={accept} /> : null}
    {view === 'suggestions' && !profile ? <div className="empty">请先完成模板映射，才能识别产品列</div> : null}
    {view === 'mapping' ? <MappingPanel host={host} api={api} profiles={profiles}
      profile={profile} onSelected={selectProfile} onSaved={saveProfile} /> : null}
    {view === 'binding' && profile ? <BindingPanel api={api} host={host} profile={profile} metadata={metadata} onBound={saveBinding} /> : null}
    {view === 'binding' && !profile ? <div className="empty">请先保存模板映射</div> : null}
    {view === 'sync' && profile ? <SyncPanel api={api} host={host} profile={profile} metadata={metadata} onSynced={setMetadata} /> : null}
    {view === 'sync' && !profile ? <div className="empty">请先保存模板映射</div> : null}
  </main>;
}

function Tab({ icon, label, active, onClick }: {
  icon: React.ReactNode; label: string; active: boolean; onClick: () => void;
}) {
  return <button className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={onClick}>
    {icon}<span>{label}</span>
  </button>;
}
