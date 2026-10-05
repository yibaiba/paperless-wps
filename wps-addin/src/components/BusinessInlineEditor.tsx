import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { WpsApi } from '../api';
import type { CompletionPreviewResult, NextEditSuggestion, ResolutionAction } from '../businessTypes';
import { completionRequest } from '../businessWorkbook';
import { businessDiagnostic } from '../businessDiagnostics';
import { BusinessPrefetch, businessPrefetchKey } from '../businessPrefetch';
import { businessCompletionGhost, businessCompletionSelection, resolvedBusinessChoice } from '../businessCompletion';
import { AppliedCompletionRefreshError, UndoneCompletionRefreshError, applyBusinessCompletion,
  resolveBusinessChoice, undoBusinessCompletion } from '../businessCompletionActions';
import { SUGGESTION_DEBOUNCE_MS } from '../constants';
import { WpsHostAdapter } from '../host';
import { LatestRequest } from '../latestRequest';
import { BUSINESS_CANDIDATE_ROW_HEIGHT, INLINE_ERROR_STATUS_ROWS } from '../inlineLayout';
import { nextEditAction } from '../nextEditState';
import { locatedChoiceRequest, locatedProductChoice, type LocatedProductChoice } from '../locatedProductChoice';
import { isProductInputCell } from '../productInput';
import { verifiedEditTarget } from '../nextEditTarget';
import { dismissedMetadata, recentHistoryKey } from '../recentBusinessEdits';
import { nextEditNotice, NEXT_EDIT_NOTICE_ROWS } from '../nextEditPresentation';
import { handleInlineTab } from '../nativeTab';
import { assertInlineSession, writeInlineInput } from '../workbookSession';
import { WorkbookRowIndex } from '../workbookRowIndex';
import { NextEditPreview, issueText } from './NextEditPreview';
import { NextEditNotice } from './NextEditNotice';
import { BusinessCandidateList } from './BusinessCandidateList';
import { decisionText } from '../businessContextPresentation';
import { navigateResolution } from '../resolutionActions';
import { IssueActions } from './IssueActions';

const POSITION_POLL_MS = 300;
const ISSUE_ACTION_STATUS_ROWS = 3;

export function BusinessInlineEditor({ host: suppliedHost, api: suppliedApi }: {
  host?: WpsHostAdapter; api?: Pick<WpsApi, 'completionPreview'>;
} = {}) {
  const host = useMemo(() => suppliedHost ?? new WpsHostAdapter(), [suppliedHost]);
  const api = useMemo(() => suppliedApi ?? new WpsApi(() => host.token()), [host, suppliedApi]);
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
  const located = useRef(false);
  const locatedChoice = useRef<LocatedProductChoice | undefined>(undefined);
  const previewOperation = useRef('');
  const index = useMemo(() => context && new WorkbookRowIndex(host, context.profile),
    [host, context?.workbook_key, context?.profile.id, context?.profile.revision]);
  const item = result?.items[selected];
  const ready = Boolean(item && !busy && !error && !writeError && !composing && !preview);
  const notice = context && ready ? nextEditNotice({ suggestion: item, cell: context.cell, query,
    target: result?.primary_suggestion_id === item?.id ? result?.next_target : undefined }) : undefined;

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
    requests.current.cancel(); setResult(undefined); setQuery(located.current ? '' : context?.cell.value ?? '');
    located.current = false;
    setError(''); setWriteError(''); setExpanded(false); setPreview(false); setExplicit(false); setSelected(0);
    setComposing(false);
  }, [context?.nonce]);
  useEffect(() => { if (!preview) input.current?.focus(); }, [context?.nonce, preview]);
  useEffect(() => {
    if (!index) return;
    return host.onSheetChange((event) => {
      // Plugin transactions refresh their affected rows once after completion.
      if (changing.current) return;
      locatedChoice.current = undefined; requests.current.cancel(); prefetch.current.clear();
      setResult(undefined); setPreview(false);
      try {
        host.restoreNativeTab();
        index.changed(event, { historyKey: recentHistoryKey(host.readMetadata()) });
        setError(''); setEpoch((v) => v + 1);
      } catch (reason) { setError(`刷新工作簿变更失败：${reason}`); }
    });
  }, [host, index]);
  useEffect(() => {
    if (!context || !index || composing || writeError || error) { host.restoreNativeTab(); setBusy(false); return; }
    setResult(undefined); setBusy(true); setError(''); setExplicit(false); setSelected(0);
    return requests.current.schedule(query ? SUGGESTION_DEBOUNCE_MS : 0, async (request) => {
      const started = performance.now();
      businessDiagnostic(host, { event_type: 'query_start', template_profile_id: context.profile.id,
        template_profile_revision: context.profile.revision });
      try {
        assertInlineSession(host, context);
        const metadata = host.readMetadata();
        if (!metadata.binding) throw new Error('请先绑定项目');
        const choice = locatedChoiceRequest({ choice: locatedChoice.current, context,
          localRevision: host.businessRevision(), query });
        if (!choice) locatedChoice.current = undefined;
        const key = businessPrefetchKey({ context, binding: metadata.binding,
          localRevision: host.businessRevision(), versions: versions.current });
        const pending = !query && !choice && prefetch.current.take(key, request.signal);
        const cached = pending && await pending;
        if (cached && 'error' in cached) throw cached.error;
        const value = cached ? cached.value : await api.completionPreview({ ...completionRequest({ host,
          profile: context.profile, metadata, cell: context.cell, index, query }), ...choice }, request.signal);
        if (!request.isCurrent()) return;
        assertInlineSession(host, context);
        if (value.local_revision !== host.businessRevision()) { setEpoch((v) => v + 1); return; }
        setResult(value);
        const selection = businessCompletionSelection({ result: value, cell: context.cell, query });
        setSelected(selection.index); setExpanded(selection.expanded);
        versions.current = value.versions;
        businessDiagnostic(host, { event_type: 'query_success', duration_ms: Math.round(performance.now() - started),
          candidate_count: value.items.length, template_profile_id: context.profile.id,
          template_profile_revision: context.profile.revision });
        if (value.items.length) businessDiagnostic(host, { event_type: 'completion_shown', completion_ready: value.items[selection.index].applicable });
        if (!value.items.length && !value.issues.length) host.hideInlineEditor();
      } catch (reason) { if (request.isCurrent()) {
        setError(String(reason));
        businessDiagnostic(host, { event_type: 'query_error', duration_ms: Math.round(performance.now() - started),
          outcome: 'failure', error_code: 'BUSINESS_PREVIEW_FAILED' });
      } }
      finally { if (request.isCurrent()) setBusy(false); }
    });
  }, [api, host, context, index, query, composing, epoch, writeError, error]);

  const apply = useCallback((suggestion: NextEditSuggestion, operationId: string) => {
    if (!context || processing.current) return;
    processing.current = true; changing.current = true;
    try {
      assertInlineSession(host, context);
      applyBusinessCompletion({ host, suggestion, operationId, afterApply: (metadata) => {
        locatedChoice.current = undefined;
        setPreview(false); setResult(undefined); setBusy(false); requests.current.cancel(); host.restoreNativeTab();
        setQuery('');
        index?.refreshRows(suggestion.patches);
        if (index && metadata.binding) {
          const payload = completionRequest({ host, profile: context.profile, metadata, cell: context.cell, index, query: '' });
          prefetch.current.start(businessPrefetchKey({ context, binding: metadata.binding,
            localRevision: host.businessRevision(), versions: versions.current }),
          (signal) => api.completionPreview(payload, signal));
        }
        // Stay at this edit. The next response supplies an actual target; Tab only locates it.
        setEpoch((value) => value + 1);
      } });
    } catch (reason) {
      if (reason instanceof AppliedCompletionRefreshError) setError(reason.message);
      else setWriteError(String(reason));
    }
    finally { processing.current = false; changing.current = false; }
  }, [api, context, host, index]);
  useEffect(() => () => { prefetch.current.clear(); requests.current.cancel(); }, []);

  const undo = useCallback(() => {
    if (!context || processing.current) return;
    processing.current = true; changing.current = true;
    locatedChoice.current = undefined;
    setResult(undefined); setPreview(false); setBusy(false); setError(''); setWriteError('');
    try {
      requests.current.cancel(); prefetch.current.clear(); host.restoreNativeTab(context.session_id);
      assertInlineSession(host, context);
      const journal = host.journals().filter((entry) => entry.state === 'applied').at(-1);
      if (journal) undoBusinessCompletion({ host, journal, afterUndo: () => {
        index?.refreshRows(journal.patches);
        if (journal.patches.some((p) => p.sheet === context.cell.sheet
          && p.row === context.cell.row && p.column === context.cell.column)) {
          setQuery(host.readCell(context.cell).value);
        }
      } });
      setEpoch((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof UndoneCompletionRefreshError ? reason.message : String(reason));
    } finally { processing.current = false; changing.current = false; }
  }, [context, host, index]);

  const dispatch = useCallback((options: {
    action: ReturnType<typeof nextEditAction>; suggestion: NextEditSuggestion;
    operationId: string; result: CompletionPreviewResult; explicitChoice?: boolean;
  }) => {
    if (!context) return;
    const { action, suggestion, operationId } = options;
    if (action === 'apply') { apply(suggestion, operationId); return; }
    if (action === 'expand') { setExpanded(true); setExplicit(false); }
    if (action === 'preview') { previewOperation.current = operationId; setPreview(true); }
    if (action === 'locate') {
      try {
        assertInlineSession(host, context);
        const target = verifiedEditTarget({ host, result: options.result, suggestion });
        located.current = true;
        prefetch.current.clear(); locatedChoice.current = undefined;
        host.selectCell(target); host.showInlineEditor(context.profile, target);
        if (options.explicitChoice) locatedChoice.current = locatedProductChoice({ context: host.inlineContext(), suggestion });
        refresh();
      } catch (reason) { located.current = false; locatedChoice.current = undefined; setError(String(reason)); }
    }
    host.restoreNativeTab(context.session_id);
  }, [apply, context, host, refresh]);

  const choose = useCallback(async (suggestion: NextEditSuggestion, claimedOperation?: string) => {
    if (!context || !index || !result || !ready || composing) return;
    const operationId = claimedOperation ?? host.claimTab(context.session_id);
    if (!operationId) return;
    const binding = suggestion.line_bindings[0];
    if (!binding) {
      const action = nextEditAction({ suggestion, cell: context.cell, query, ready: true,
        composing: false, explicit: true, count: 1,
        target: result.primary_suggestion_id === suggestion.id ? result.next_target : undefined });
      dispatch({ action, suggestion, operationId, result }); return;
    }
    const request = requests.current.begin();
    setBusy(true); setError(''); host.restoreNativeTab();
    try {
      const value = await resolveBusinessChoice({ host, context, request, load: (signal) =>
        api.completionPreview({ ...completionRequest({ host, profile: context.profile,
          metadata: host.readMetadata(), cell: context.cell, index, query }),
          selected_variant_id: binding.variant_id, selected_source_id: binding.source_id }, signal) });
      if (!value) return;
      const selection = resolvedBusinessChoice({ result: value, cell: context.cell, query });
      setResult(value); setSelected(selection.index); setExplicit(value.items.length === 1);
      setExpanded(selection.action === 'expand'); versions.current = value.versions;
      const selectedItem = value.items[selection.index];
      if (selectedItem) dispatch({ ...selection, suggestion: selectedItem, operationId, result: value, explicitChoice: true });
      else if (!value.issues.length) host.hideInlineEditor();
    } catch (reason) { if (request.isCurrent()) setError(String(reason)); }
    finally { if (request.isCurrent()) setBusy(false); }
  }, [api, composing, context, dispatch, host, index, query, ready, result]);

  const tab = useCallback(() => {
    if (!context || composing) return;
    const action = nextEditAction({ suggestion: item, cell: context.cell, ready,
      composing, explicit, count: result?.items.length ?? 0, query,
      primarySuggestionId: result?.primary_suggestion_id, decision: result?.decision,
      target: result?.primary_suggestion_id === item?.id ? result?.next_target : undefined });
    if (action === 'native') { host.returnNativeTab(false); return; }
    const operationId = host.claimTab(context.session_id);
    if (!operationId || !item || !result) return;
    if (explicit && expanded) { void choose(item, operationId); return; }
    dispatch({ action, suggestion: item, operationId, result });
  }, [choose, composing, context, dispatch, expanded, explicit, host, item, ready, result, query]);

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
      const statusRows = (notice && !expanded ? NEXT_EDIT_NOTICE_ROWS : 0)
        + Number(Boolean(error)) * INLINE_ERROR_STATUS_ROWS
        + Number(Boolean(writeError)) * INLINE_ERROR_STATUS_ROWS
        + Number(!error && Boolean(result?.issues.length)) * ISSUE_ACTION_STATUS_ROWS;
      try { setPlacement(host.layoutInlineEditor({ candidateCount: preview ? 4 : result?.items.length ?? 0,
        listVisible: expanded || preview, showStatus: statusRows > 0 || Boolean(result?.decision),
        statusRows: statusRows + Number(Boolean(result?.decision && !preview)),
        candidateRowHeight: preview ? undefined : BUSINESS_CANDIDATE_ROW_HEIGHT,
      }).placement); } catch (reason) { setError(String(reason)); }
    };
    layout(); const timer = window.setInterval(layout, POSITION_POLL_MS);
    return () => window.clearInterval(timer);
  }, [host, context, expanded, preview, result, error, writeError, busy, Boolean(notice)]);

  if (!context) return null;
  const canType = isProductInputCell(context.profile, context.cell);
  const ghost = businessCompletionGhost({ result, index: selected, cell: context.cell, query, ready, explicit });
  const previewAction = nextEditAction({ suggestion: item, cell: context.cell, query, ready: true,
    composing, explicit: true, count: 1,
    target: result?.primary_suggestion_id === item?.id ? result?.next_target : undefined });
  const closePreview = () => setPreview(false);
  const resolveIssue = (action: ResolutionAction) => {
    try {
      assertInlineSession(host, context);
      requests.current.cancel(); prefetch.current.clear();
      navigateResolution({ host, action, fingerprint: result!.context_fingerprint });
    } catch (reason) { setError(String(reason)); }
  };
  return <div className={`inline-editor ${placement}`}>
    <div className="inline-input-row"><div className="inline-query">
      {!expanded && ghost && <div className="inline-ghost" aria-hidden="true"><span>{ghost.prefix}</span>{ghost.suffix}</div>}
      <input ref={input} aria-label="当前单元格产品输入" value={query} role="combobox"
        readOnly={!canType}
        aria-autocomplete="both" aria-expanded={expanded && !preview} aria-busy={busy}
        aria-controls="business-candidates" autoComplete="off" placeholder={canType ? '输入型号或名称' : 'Tab 查看修改预览'}
        aria-activedescendant={expanded && !preview && item ? `business-candidate-${selected}` : undefined}
        onCompositionStart={() => { setComposing(true); requests.current.cancel(); host.restoreNativeTab(); }}
        onCompositionEnd={(e) => { setQuery(e.currentTarget.value); setComposing(false); }}
        onChange={(e) => {
          locatedChoice.current = undefined;
          requests.current.cancel(); host.restoreNativeTab(); setResult(undefined); setPreview(false); setExpanded(false); setError('');
          setQuery(e.target.value); changing.current = true;
          try {
            writeInlineInput({ host, context, value: e.target.value });
            index?.refresh(context.cell.row); setWriteError('');
          }
          catch (reason) { setWriteError(String(reason)); }
          finally { changing.current = false; }
        }} onKeyDown={(e) => {
          if (composing || e.nativeEvent.isComposing) return;
          if (e.key === 'Escape') {
            e.preventDefault();
            if (preview) { closePreview(); return; }
            try {
              assertInlineSession(host, context);
              const metadata = host.readMetadata();
              if (ready && item && metadata.business) host.writeMetadata(dismissedMetadata({
                metadata, suggestion: item, operationId: crypto.randomUUID(),
              }));
              requests.current.cancel(); prefetch.current.clear(); host.restoreNativeTab();
              host.hideInlineEditor();
            } catch (reason) { setError(String(reason)); }
          }
          if (e.key === 'Tab') {
            e.preventDefault();
            try { handleInlineTab({ ready, shift: e.shiftKey, complete: tab,
              native: (shift) => host.returnNativeTab(shift) }); }
            catch (reason) { host.reportBackgroundError(`原生 Tab 交还失败：${reason}`); setError(String(reason)); }
          }
          if (['ArrowDown', 'ArrowUp'].includes(e.key) && result?.items.length) {
            e.preventDefault(); setExpanded(true); setExplicit(true);
            setSelected((n) => (n + (e.key === 'ArrowDown' ? 1 : -1) + result.items.length) % result.items.length);
          }
          if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
            e.preventDefault(); undo();
          }
          if (e.key === 'Enter' && ready && expanded && item) { e.preventDefault(); void choose(item); }
        }} /></div>{ghost && !expanded && <kbd>Tab</kbd>}{busy && <span className="inline-busy" aria-label="正在查询" />}</div>
    {error && <div className="inline-error" role="alert">{error}
      <button type="button" onClick={() => {
        requests.current.cancel(); prefetch.current.clear(); setError(''); setEpoch((v) => v + 1); input.current?.focus();
      }}>重试查询</button>
    </div>}
    {writeError && <div className="inline-error" role="alert">修改未完成：{writeError}</div>}
    {ready && !expanded && <NextEditNotice notice={notice} />}
    {result?.decision && !preview && <div className="inline-status" role="status">{decisionText(result.decision)}
      {item && ready && <button type="button" onClick={() => {
        const operationId = host.claimTab(context.session_id);
        if (operationId) dispatch({ action: 'preview', suggestion: item, operationId, result });
      }}>查看依据</button>}
    </div>}
    {!error && Boolean(result?.issues.length) && <div className="inline-status" title={result!.issues.map(issueText).join('；')}>
      <IssueActions issue={result!.issues[0]} onResolve={resolveIssue} />
    </div>}
    {expanded && !preview && <BusinessCandidateList items={result?.items ?? []} selected={selected}
      column={context.cell.column} ready={ready}
      onChoose={(candidate, i) => { setSelected(i); void choose(candidate); }} />}
    {preview && item && <div className="inline-business-preview"><NextEditPreview suggestion={item}
      contextSummary={result?.context_summary}
      applyLabel={previewAction === 'locate' ? '定位目标后重新预览' : undefined}
      autoFocus onCancel={closePreview} onApply={() => {
        if (previewAction === 'locate' && result) dispatch({ action: 'locate', suggestion: item,
          operationId: previewOperation.current, result });
        else apply(item, previewOperation.current);
      }} /></div>}
  </div>;
}
