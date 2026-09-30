import {
  useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState,
} from 'react';

import { WpsApi } from '../api';
import { applyCandidate } from '../candidateAcceptance';
import { completionFeedbackPayload } from '../completionFeedback';
import { CompletionPrefetch } from '../completionPrefetch';
import {
  candidateIsAmbiguous,
  completionCommand,
  completionKey,
  completionPhase,
  EMPTY_SELECTION,
  navigateCandidates,
  selectionForCandidates,
  suggestionDelay,
  type CompletionSelection,
} from '../completionState';
import { WpsHostAdapter } from '../host';
import { ghostCompletion } from '../inlineCompletion';
import type { InlineLayoutOptions, InlinePlacement, InlineLayoutResult } from '../inlineLayout';
import {
  INLINE_CANDIDATE_LIMIT,
  inlineContextKey,
  readInlineWorkbookContext,
  startNextRowPrefetch,
} from '../inlineSuggestionSession';
import { LatestRequest } from '../latestRequest';
import type { Candidate, DiagnosticEventInput, InlineEditorContext } from '../types';

const POSITION_POLL_MS = 300;
const CANDIDATE_LIST_ID = 'product-candidates';

const GROUP_LABELS: Record<Candidate['group'], string> = {
  direct: '直接', series: '同系列', alternative: '替代', accessory: '配套', related: '相关',
};
const BLOCKER_MESSAGES: Partial<Record<NonNullable<Candidate['completion_blocker']>, string>> = {
  template_source_unconfirmed: '请先在模板设置中确认产品来源',
  source_ambiguous: '存在多个资料来源，请明确选择',
  variant_ambiguous: '存在多个产品配置，请明确选择',
  insufficient_evidence: '上下文证据不足，请明确选择',
  insufficient_margin: '候选过于接近，请明确选择',
};

export function InlineEditor() {
  const host = useMemo(() => new WpsHostAdapter(), []);
  const api = useMemo(() => new WpsApi(() => host.token()), [host]);
  const [context, setContext] = useState<InlineEditorContext | null>(() => host.inlineContext());
  const [query, setQuery] = useState(() => context?.cell.value ?? '');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selection, setSelection] = useState<CompletionSelection>(EMPTY_SELECTION);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [composing, setComposing] = useState(false);
  const [placement, setPlacement] = useState<InlinePlacement>('below');
  const [anchorHeight, setAnchorHeight] = useState(context?.anchor.height ?? 32);
  const [tabGeneration, setTabGeneration] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const requests = useRef(new LatestRequest());
  const accepting = useRef(false);
  const prefetch = useRef(new CompletionPrefetch<Candidate[]>());
  const contextNonce = useRef(context?.nonce ?? 0);
  const windowChromeHeight = useRef(Math.max(0, window.outerHeight - window.innerHeight));
  const workbookContext = useMemo(
    () => context && readInlineWorkbookContext(host, context),
    [context, host],
  );
  const diagnose = useCallback((value: DiagnosticEventInput) => {
    try { host.recordDiagnostic(value); }
    catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      host.reportBackgroundError(`WPS 诊断记录失败：${message}`);
    }
  }, [host]);

  const refreshContext = useCallback(() => {
    const next = host.inlineContext();
    if (!next) {
      if (!contextNonce.current) return;
      contextNonce.current = 0;
      requests.current.cancel();
      setContext(null);
      setCandidates([]);
      setBusy(false);
      return;
    }
    if (next.nonce === contextNonce.current) return;
    contextNonce.current = next.nonce;
    setContext(next);
    setAnchorHeight(next.anchor.height);
    setQuery(next.cell.value);
    setCandidates([]);
    setSelection(EMPTY_SELECTION);
    setTabGeneration(0);
    accepting.current = false;
    setError('');
    diagnose({
      event_type: 'inline_open',
      template_profile_id: next.profile.id,
      template_profile_revision: next.profile.revision,
      outcome: 'success',
    });
    window.setTimeout(() => input.current?.focus(), 0);
  }, [diagnose, host]);

  useEffect(() => {
    window.PresalesInlineRefresh = refreshContext;
    window.addEventListener('focus', refreshContext);
    return () => {
      window.removeEventListener('focus', refreshContext);
      delete window.PresalesInlineRefresh;
    };
  }, [refreshContext]);

  useEffect(() => {
    if (!context) return undefined;
    const onBlur = () => diagnose({
      event_type: 'focus_lost',
      template_profile_id: context.profile.id,
      template_profile_revision: context.profile.revision,
    });
    window.addEventListener('blur', onBlur);
    return () => window.removeEventListener('blur', onBlur);
  }, [context, diagnose]);

  useEffect(() => {
    input.current?.focus();
    if (!context || !workbookContext || composing) {
      requests.current.cancel();
      setCandidates([]);
      setBusy(false);
      return undefined;
    }
    if ('error' in workbookContext) {
      setError(workbookContext.error ?? '读取工作簿上下文失败');
      return undefined;
    }
    const { metadata, row, product: productContext } = workbookContext.value;
    const hasSequenceContext = productContext.previous_variant_ids.length > 0
      || productContext.next_variant_ids.length > 0
      || Boolean(productContext.selected_variant_id);
    if (!query.trim() && !hasSequenceContext) {
      requests.current.cancel();
      setCandidates([]);
      setBusy(false);
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      const request = requests.current.begin();
      const started = performance.now();
      setBusy(true);
      setError('');
      diagnose({
        event_type: 'query_start',
        completion_phase: 'loading',
        template_profile_id: context.profile.id,
        template_profile_revision: context.profile.revision,
      });
      try {
        const key = inlineContextKey(context, metadata);
        const pending = query.trim() ? undefined : prefetch.current.take(key);
        const prefetched = pending ? await pending : undefined;
        if (prefetched && 'error' in prefetched) throw prefetched.error;
        const result = prefetched ? { items: prefetched.value } : await api.suggestions({
          query: query.trim(),
          workbook_instance_id: metadata.workbook_instance_id,
          template_profile_id: context.profile.id,
          template_profile_revision: context.profile.revision,
          draft_id: metadata.binding?.draft_id,
          current_row: row?.values ?? {},
          context: productContext,
        }, request.signal);
        if (!request.isCurrent()) return;
        const next = result.items.slice(0, INLINE_CANDIDATE_LIMIT);
        setCandidates(next);
        const durationMs = Math.round(performance.now() - started);
        diagnose({
          event_type: 'query_success',
          completion_phase: next.length ? 'typing' : 'no-match',
          duration_ms: durationMs,
          candidate_count: next.length,
          completion_ready: Boolean(next[0]?.completion_ready),
          outcome: 'success',
          template_profile_id: context.profile.id,
          template_profile_revision: context.profile.revision,
        });
        if (!next.length) diagnose({
          event_type: 'no_match', completion_phase: 'no-match', candidate_count: 0,
          template_profile_id: context.profile.id,
          template_profile_revision: context.profile.revision,
        });
        const preferredField = context.profile.field_columns.model === context.cell.column
          ? 'model' : 'name';
        setSelection(selectionForCandidates(query, next, preferredField));
      } catch (reason) {
        if (request.isCurrent()) {
          diagnose({
            event_type: 'query_error',
            completion_phase: 'error',
            duration_ms: Math.round(performance.now() - started),
            outcome: 'failure',
            error_code: 'suggestion_request_failed',
            template_profile_id: context.profile.id,
            template_profile_revision: context.profile.revision,
          });
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      } finally {
        if (request.isCurrent()) setBusy(false);
      }
    }, suggestionDelay(query));
    return () => window.clearTimeout(timer);
  }, [api, composing, context, diagnose, query, workbookContext]);

  const selectedCandidate = candidates[selection.index];
  const preferredField = context?.profile.field_columns.model === context?.cell.column
    ? 'model' : 'name';
  const ghost = ghostCompletion(query, selectedCandidate, preferredField);
  const listVisible = selection.expanded && candidates.length > 0;
  const ambiguous = candidateIsAmbiguous(candidates, selection.index, query);
  const needsChoice = listVisible && !selection.explicit && (ambiguous || !ghost);
  const phase = completionPhase({
    busy, error, candidates, selection, hasGhost: Boolean(ghost), query,
  });
  const layout = useMemo<Omit<InlineLayoutOptions, 'anchorWidth' | 'anchorHeight'>>(() => ({
    candidateCount: candidates.length,
    listVisible,
    showStatus: Boolean(error) || needsChoice,
    windowChromeHeight: windowChromeHeight.current,
  }), [ambiguous, candidates.length, error, listVisible, needsChoice]);
  const layoutRef = useRef(layout);
  layoutRef.current = layout;

  const applyLayout = useCallback((result: InlineLayoutResult) => {
    setPlacement(result.placement);
    setAnchorHeight(result.anchor.height);
  }, []);

  useLayoutEffect(() => {
    applyLayout(host.layoutInlineEditor(layout));
  }, [applyLayout, host, layout]);

  useEffect(() => {
    const poll = window.setInterval(() => {
      applyLayout(host.layoutInlineEditor(layoutRef.current));
    }, POSITION_POLL_MS);
    return () => window.clearInterval(poll);
  }, [applyLayout, host]);

  const prefetchNextRow = useCallback((metadata: ReturnType<typeof applyCandidate>) => {
    if (!context) return;
    startNextRowPrefetch({
      api, host, context, metadata, prefetch: prefetch.current,
    });
  }, [api, context, host]);

  const accept = useCallback((
    candidate: Candidate,
    advance = false,
    operationId: string = crypto.randomUUID(),
  ) => {
    if (accepting.current || !context || !workbookContext || 'error' in workbookContext) return;
    accepting.current = true;
    try {
      const feedback = completionFeedbackPayload({
        operationId,
        context,
        metadata: workbookContext.value.metadata,
        productContext: workbookContext.value.product,
        query,
        candidates,
        chosen: candidate,
      });
      const metadata = applyCandidate(
        host, context.profile, context.cell, host.readMetadata(), candidate,
      );
      if (feedback) {
        try {
          host.enqueueSuggestionFeedback(feedback);
          void api.suggestionFeedback(feedback).then(() => {
            host.removeSuggestionFeedback(feedback.operation_id);
          }).catch((reason) => {
            const message = reason instanceof Error ? reason.message : String(reason);
            host.reportBackgroundError(`产品顺序学习失败：${message}`);
          });
        } catch (reason) {
          const message = reason instanceof Error ? reason.message : String(reason);
          host.reportBackgroundError(`产品顺序学习失败：${message}`);
        }
      }
      if (advance) {
        prefetchNextRow(metadata);
      }
      diagnose({
        event_type: 'accept_success',
        completion_phase: phase,
        outcome: 'success',
        template_profile_id: context.profile.id,
        template_profile_revision: context.profile.revision,
      });
      host.hideInlineEditor();
      if (advance) {
        try { host.moveSelection(1, 0); }
        catch (reason) {
          const message = reason instanceof Error ? reason.message : String(reason);
          host.reportBackgroundError(`移动到下一产品行失败：${message}`);
        }
      }
    } catch (reason) {
      accepting.current = false;
      diagnose({
        event_type: 'accept_error',
        completion_phase: 'error',
        outcome: 'failure',
        error_code: 'candidate_write_failed',
        template_profile_id: context.profile.id,
        template_profile_revision: context.profile.revision,
      });
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [api, candidates, context, diagnose, host, phase, prefetchNextRow, query, workbookContext]);

  const executeCompletion = useCallback((
    key: 'Tab' | 'Enter',
    operationId: string = crypto.randomUUID(),
  ) => {
    const command = completionCommand({
      key, candidates, selection, hasGhost: Boolean(ghost), query,
    });
    if (command === 'expand') {
      if (key === 'Tab') diagnose({
        event_type: 'tab_expand', completion_phase: phase, outcome: 'expanded',
        template_profile_id: context?.profile.id,
        template_profile_revision: context?.profile.revision,
      });
      setSelection((current) => ({ ...current, expanded: true }));
      setTabGeneration((current) => current + 1);
    } else if (command === 'accept' && selectedCandidate) {
      if (key === 'Tab') diagnose({
        event_type: 'tab_accept', completion_phase: phase,
        candidate_count: candidates.length, completion_ready: selectedCandidate.completion_ready,
        template_profile_id: context?.profile.id,
        template_profile_revision: context?.profile.revision,
      });
      accept(selectedCandidate, key === 'Tab', operationId);
    } else if (command === 'native-tab') {
      host.hideInlineEditor();
      host.moveSelection(0, 1);
    }
    return command;
  }, [
    accept, candidates, context, diagnose, ghost, host, phase, query, selectedCandidate, selection,
  ]);

  const dispatchTab = useCallback((expectedSessionId: string) => {
    if (!context || context.session_id !== expectedSessionId) return;
    try {
      const operationId = host.claimTab(context.session_id);
      if (!operationId) return;
      executeCompletion('Tab', operationId);
    } catch (reason) {
      host.restoreNativeTab(context.session_id);
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [context, executeCompletion, host]);

  useEffect(() => {
    window.PresalesInlineTab = dispatchTab;
    return () => { delete window.PresalesInlineTab; };
  }, [dispatchTab]);

  useEffect(() => {
    if (!context) return undefined;
    const command = completionCommand({
      key: 'Tab', candidates, selection, hasGhost: Boolean(ghost), query,
    });
    const actionable = !busy && !error && !composing
      && (command === 'accept' || command === 'expand');
    if (!actionable) {
      if (host.restoreNativeTab(context.session_id)) diagnose({
        event_type: 'tab_restore', completion_phase: phase, outcome: 'restored',
        template_profile_id: context.profile.id,
        template_profile_revision: context.profile.revision,
      });
      return undefined;
    }
    const revision = [
      phase, selection.index, Number(selection.expanded), Number(selection.explicit),
      candidates[0]?.key ?? '', tabGeneration,
    ].join(':');
    if (host.interceptTab(context.session_id, revision)) diagnose({
      event_type: 'tab_register', completion_phase: phase,
      template_profile_id: context.profile.id,
      template_profile_revision: context.profile.revision,
    });
    return () => {
      if (host.restoreNativeTab(context.session_id)) diagnose({
        event_type: 'tab_restore', completion_phase: phase, outcome: 'restored',
        template_profile_id: context.profile.id,
        template_profile_revision: context.profile.revision,
      });
    };
  }, [
    busy, candidates, composing, context, diagnose, error, ghost, host, phase, query, selection,
    tabGeneration,
  ]);

  function updateQuery(value: string) {
    if (!context) return;
    requests.current.cancel();
    setQuery(value);
    setCandidates([]);
    setSelection(EMPTY_SELECTION);
    setError('');
    try { host.writeCellValue(context.cell, value); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    const key = completionKey(event.key, event.nativeEvent.isComposing);
    if (!key) return;
    if (key === 'ArrowDown' || key === 'ArrowUp') {
      if (candidates.length === 0) return;
      event.preventDefault();
      setSelection((current) => navigateCandidates(
        current, candidates.length, key === 'ArrowDown' ? 1 : -1,
      ));
      return;
    }
    if (key === 'Escape') {
      event.preventDefault();
      host.hideInlineEditor();
      return;
    }
    const command = completionCommand({ key, candidates, selection, hasGhost: Boolean(ghost), query });
    if (command === 'none') return;
    event.preventDefault();
    if (key === 'Tab' && command !== 'native-tab' && context) {
      dispatchTab(context.session_id);
    }
    else executeCompletion(key);
  }

  if (!context) return <main className="inline-empty">重新选择产品单元格</main>;

  const choiceMessage = selectedCandidate?.completion_blocker
    ? BLOCKER_MESSAGES[selectedCandidate.completion_blocker]
    : ambiguous ? '存在同名型号或多个配置，请明确选择' : '请选择要补全的产品';

  return <main className={`inline-editor ${placement}`} data-phase={phase}
    data-row={context.cell.row} data-column={context.cell.column}
    style={{ '--anchor-height': `${anchorHeight}px` } as React.CSSProperties}>
    <div className="inline-input-row">
      <div className="inline-query">
        {ghost ? <span className="inline-ghost" aria-hidden="true">
          <span>{ghost.prefix}</span>{ghost.suffix}
        </span> : null}
        <input ref={input} value={query} onChange={(event) => updateQuery(event.target.value)}
          onKeyDown={handleKeyDown} role="combobox" aria-label="产品型号或名称"
          aria-autocomplete="both" aria-controls={CANDIDATE_LIST_ID}
          aria-expanded={listVisible} aria-busy={busy}
          aria-activedescendant={listVisible && selectedCandidate
            ? `candidate-${selection.index}` : undefined}
          autoComplete="off" placeholder={ghost ? '' : '输入型号或名称'}
          onCompositionStart={() => { requests.current.cancel(); setComposing(true); }}
          onCompositionEnd={(event) => { updateQuery(event.currentTarget.value); setComposing(false); }} />
      </div>
      {ghost && !listVisible ? <kbd>Tab</kbd> : null}
      {busy ? <span className="inline-busy" aria-hidden="true" /> : null}
    </div>
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    {!error && needsChoice
      ? <div className="inline-status" role="status">{choiceMessage}</div> : null}
    {listVisible ? <div id={CANDIDATE_LIST_ID} className="inline-candidates"
      role="listbox" aria-label="产品候选">
      {candidates.map((candidate, index) => <button id={`candidate-${index}`}
        type="button" role="option"
        aria-selected={index === selection.index}
        className={index === selection.index ? 'selected' : ''}
        key={candidate.key} onMouseDown={(event) => event.preventDefault()}
        onClick={() => accept(candidate)}
        onMouseEnter={() => setSelection({ expanded: true, explicit: true, index })}
        title={[candidate.model, candidate.variant_name, ...candidate.context_reasons].join(' · ')}>
        <span className="candidate-copy">
          <strong>{candidate.name}</strong>
          <span>{candidate.model}<small>{candidate.variant_name}</small></span>
        </span>
        <span className={`candidate-kind ${candidate.group}`}>{GROUP_LABELS[candidate.group]}</span>
      </button>)}
    </div> : null}
  </main>;
}
