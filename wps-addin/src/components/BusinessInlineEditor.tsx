import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { WpsApi } from '../api';
import type { CompletionPreviewResult, NextEditSuggestion } from '../businessTypes';
import { completionRequest } from '../businessWorkbook';
import { businessDiagnostic } from '../businessDiagnostics';
import { BusinessPrefetch, businessPrefetchKey } from '../businessPrefetch';
import { SUGGESTION_DEBOUNCE_MS } from '../constants';
import { applyNextEdit, restoreJournal } from '../editJournal';
import { WpsHostAdapter } from '../host';
import { LatestRequest } from '../latestRequest';
import { nextEditAction, nextEditText } from '../nextEditState';
import { WorkbookRowIndex } from '../workbookRowIndex';
import { NextEditPreview, issueText } from './NextEditPreview';

const POSITION_POLL_MS = 300;

export function BusinessInlineEditor() {
  const host = useMemo(() => new WpsHostAdapter(), []);
  const api = useMemo(() => new WpsApi(() => host.token()), [host]);
  const [context, setContext] = useState(() => host.inlineContext());
  const [query, setQuery] = useState(context?.cell.value ?? '');
  const [result, setResult] = useState<CompletionPreviewResult>();
  const [selected, setSelected] = useState(0);
  const [explicit, setExplicit] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [composing, setComposing] = useState(false);
  const [error, setError] = useState('');
  const [writeError, setWriteError] = useState('');
  const [epoch, setEpoch] = useState(0);
  const [placement, setPlacement] = useState('below');
  const requests = useRef(new LatestRequest());
  const prefetch = useRef(new BusinessPrefetch());
  const versions = useRef<CompletionPreviewResult['versions']>({});
  const input = useRef<HTMLInputElement>(null);
  const changing = useRef(false);
  const processing = useRef(false);
  const located = useRef<CompletionPreviewResult | undefined>(undefined);
  const index = useMemo(() => context && new WorkbookRowIndex(host, context.profile),
    [host, context?.workbook_key, context?.profile.id, context?.profile.revision]);
  const item = result?.items[selected];
  const ready = Boolean(item && !busy && !error && !writeError && !composing && !preview);

  const refresh = useCallback(() => {
    const next = host.inlineContext();
    setContext((old) => old?.nonce === next?.nonce ? old : next);
  }, [host]);
  useEffect(() => {
    window.PresalesInlineRefresh = refresh;
    window.addEventListener('focus', refresh);
    return () => { delete window.PresalesInlineRefresh; window.removeEventListener('focus', refresh); };
  }, [refresh]);
  useEffect(() => {
    requests.current.cancel(); setResult(undefined); setQuery(context?.cell.value ?? '');
    setError(''); setWriteError(''); setExpanded(false); setPreview(false); setExplicit(false); setSelected(0);
    input.current?.focus();
  }, [context?.nonce]);
  useEffect(() => {
    if (!index) return;
    return host.onSheetChange((event) => {
      index.changed(event);
      if (!changing.current) { requests.current.cancel(); prefetch.current.clear(); setResult(undefined); setEpoch((v) => v + 1); }
    });
  }, [host, index]);
  useEffect(() => {
    if (!context || !index || composing || writeError) { host.restoreNativeTab(); setBusy(false); return; }
    setResult(undefined); setBusy(true); setError(''); setExplicit(false); setSelected(0);
    const pending = located.current;
    if (pending && pending.local_revision === host.businessRevision()) {
      located.current = undefined;
      setResult(pending);
      setBusy(false); setExplicit(true); return;
    }
    return requests.current.schedule(query ? SUGGESTION_DEBOUNCE_MS : 0, async (request) => {
      const started = performance.now();
      businessDiagnostic(host, { event_type: 'query_start', template_profile_id: context.profile.id,
        template_profile_revision: context.profile.revision });
      try {
        const metadata = host.readMetadata();
        if (!metadata.binding) throw new Error('请先绑定项目');
        const key = businessPrefetchKey({ context, binding: metadata.binding,
          localRevision: host.businessRevision(), versions: versions.current });
        const pending = !query && prefetch.current.take(key);
        const cached = pending && await pending;
        if (cached && 'error' in cached) throw cached.error;
        const value = cached ? cached.value : await api.completionPreview(completionRequest({ host,
          profile: context.profile, metadata, cell: context.cell, index, query }), request.signal);
        if (!request.isCurrent()) return;
        if (value.local_revision !== host.businessRevision()) { setEpoch((v) => v + 1); return; }
        setResult(value);
        versions.current = value.versions;
        businessDiagnostic(host, { event_type: 'query_success', duration_ms: Math.round(performance.now() - started),
          candidate_count: value.items.length, template_profile_id: context.profile.id,
          template_profile_revision: context.profile.revision });
        if (value.items.length) businessDiagnostic(host, { event_type: 'completion_shown', completion_ready: value.items[0].applicable });
        if (!value.items.length && !value.issues.length) host.hideInlineEditor();
      } catch (reason) { if (request.isCurrent()) {
        setError(String(reason));
        businessDiagnostic(host, { event_type: 'query_error', duration_ms: Math.round(performance.now() - started),
          outcome: 'failure', error_code: 'BUSINESS_PREVIEW_FAILED' });
      } }
      finally { if (request.isCurrent()) setBusy(false); }
    });
  }, [api, host, context, index, query, composing, epoch, writeError]);

  const apply = useCallback((suggestion: NextEditSuggestion, operationId: string) => {
    if (!context || processing.current) return;
    processing.current = true; changing.current = true;
    try {
      applyNextEdit({ host, suggestion, operationId });
      suggestion.patches.forEach((p) => index?.refresh(p.row));
      setPreview(false); setResult(undefined); requests.current.cancel(); host.restoreNativeTab();
      const cell = { ...context.cell, row: context.cell.row + 1 };
      host.selectCell(cell);
      host.showInlineEditor(context.profile, host.readCell(cell));
      const next = host.inlineContext();
      const metadata = host.readMetadata();
      if (next && index && metadata.binding && !next.cell.value) {
        const payload = completionRequest({ host, profile: next.profile, metadata, cell: next.cell, index, query: '' });
        prefetch.current.start(businessPrefetchKey({ context: next, binding: metadata.binding,
          localRevision: host.businessRevision(), versions: versions.current }),
        (signal) => api.completionPreview(payload, signal));
      }
      refresh();
    } catch (reason) { setError(String(reason)); }
    finally { processing.current = false; changing.current = false; }
  }, [api, context, host, index, refresh]);
  useEffect(() => () => { prefetch.current.clear(); requests.current.cancel(); }, []);

  async function choose(suggestion: NextEditSuggestion) {
    const binding = suggestion.line_bindings[0];
    if (!context || !index || !binding) { setPreview(true); return; }
    const request = requests.current.begin();
    setBusy(true); setError(''); host.restoreNativeTab();
    try {
      const value = await api.completionPreview({ ...completionRequest({ host, profile: context.profile,
        metadata: host.readMetadata(), cell: context.cell, index, query }),
        selected_variant_id: binding.variant_id, selected_source_id: binding.source_id }, request.signal);
      if (!request.isCurrent()) return;
      if (value.local_revision !== host.businessRevision()) throw new Error('选择期间工作簿已变化，请重新查询');
      setResult(value); setSelected(0); setExplicit(true); setPreview(true);
    } catch (reason) { if (request.isCurrent()) setError(String(reason)); }
    finally { if (request.isCurrent()) setBusy(false); }
  }

  const tab = useCallback(() => {
    if (!context) return;
    const action = nextEditAction({ suggestion: item, cell: context.cell, ready,
      composing, explicit, count: result?.items.length ?? 0 });
    if (action === 'native') return;
    const operationId = host.claimTab(context.session_id);
    if (!operationId || !item) return;
    if (action === 'apply') { apply(item, operationId); return; }
    if (action === 'expand') { setExpanded(true); setExplicit(false); }
    if (action === 'preview') { setPreview(true); }
    if (action === 'locate') {
      located.current = result && { ...result, items: [item] };
      const target = { ...item.patches[0], column: context.cell.column };
      host.selectCell(target); host.showInlineEditor(context.profile, host.readCell(target)); refresh();
    }
    host.restoreNativeTab(context.session_id);
  }, [apply, composing, context, explicit, host, item, ready, refresh, result]);

  useEffect(() => {
    if (!context) return;
    if (ready) host.interceptTab(context.session_id, `${item!.id}:${selected}:${explicit}:${expanded}`);
    else host.restoreNativeTab(context.session_id);
    window.PresalesInlineTab = (session) => { if (session === context.session_id) tab(); };
    return () => { delete window.PresalesInlineTab; host.restoreNativeTab(context.session_id); };
  }, [context, explicit, expanded, host, item, ready, selected, tab]);
  useEffect(() => {
    if (!context) return;
    const layout = () => {
      try { setPlacement(host.layoutInlineEditor({ candidateCount: preview ? 4 : result?.items.length ?? 0,
        listVisible: expanded || preview, showStatus: Boolean(error || busy || result?.issues.length),
      }).placement); } catch (reason) { setError(String(reason)); }
    };
    layout(); const timer = window.setInterval(layout, POSITION_POLL_MS);
    return () => window.clearInterval(timer);
  }, [host, context, expanded, preview, result, error, busy]);

  if (!context) return null;
  const text = nextEditText(item, context.cell.column);
  const suffix = text.toLocaleLowerCase().startsWith(query.toLocaleLowerCase()) ? text.slice(query.length) : '';
  return <div className={`inline-editor ${placement}`}>
    <div className="inline-input-row"><div className="inline-query">
      {!expanded && ready && <div className="inline-ghost"><span>{query}</span>{suffix}</div>}
      <input ref={input} aria-label="当前单元格产品输入" value={query}
        onCompositionStart={() => { setComposing(true); requests.current.cancel(); host.restoreNativeTab(); }}
        onCompositionEnd={(e) => { setQuery(e.currentTarget.value); setComposing(false); }}
        onChange={(e) => {
          requests.current.cancel(); host.restoreNativeTab(); setResult(undefined); setPreview(false); setExpanded(false);
          setQuery(e.target.value); changing.current = true;
          try { host.writeCellValue(context.cell, e.target.value); index?.refresh(context.cell.row); setWriteError(''); }
          catch (reason) { setWriteError(String(reason)); }
          finally { changing.current = false; }
        }} onKeyDown={(e) => {
          if (composing || e.nativeEvent.isComposing) return;
          if (e.key === 'Escape') { e.preventDefault(); host.hideInlineEditor(); }
          if (e.key === 'Tab') {
            e.preventDefault();
            if (ready) tab(); else { host.hideInlineEditor(); host.moveSelection(0, e.shiftKey ? -1 : 1); }
          }
          if (['ArrowDown', 'ArrowUp'].includes(e.key) && result?.items.length) {
            e.preventDefault(); setExpanded(true); setExplicit(true);
            setSelected((n) => (n + (e.key === 'ArrowDown' ? 1 : -1) + result.items.length) % result.items.length);
          }
          if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            try { const journal = host.journals().filter((j) => j.state === 'applied').at(-1);
              if (journal) { restoreJournal(host, journal); setEpoch((v) => v + 1); }
            } catch (reason) { setError(String(reason)); }
          }
          if (e.key === 'Enter' && expanded && item) { e.preventDefault(); void choose(item); }
        }} /></div>{busy && <span className="inline-busy" />}</div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {writeError && <div className="inline-error" role="alert">单元格未写入：{writeError}</div>}
    {!error && Boolean(result?.issues.length) && <div className="inline-status" title={result!.issues.map(issueText).join('；')}>{issueText(result!.issues[0])}</div>}
    {expanded && !preview && <div className="inline-candidates">{result?.items.map((candidate, i) =>
      <button key={candidate.id} className={i === selected ? 'selected' : ''} onClick={() => { setSelected(i); void choose(candidate); }}>
        {nextEditText(candidate, context.cell.column)} · {candidate.patches[0]?.row ?? '用途关联'}
      </button>)}</div>}
    {preview && item && <div className="inline-business-preview"><NextEditPreview suggestion={item}
      onApply={() => apply(item, crypto.randomUUID())} /></div>}
  </div>;
}
