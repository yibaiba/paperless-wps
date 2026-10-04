import { useEffect, useRef } from 'react';
import type { CompletionContextSummary, NextEditSuggestion } from '../businessTypes';
import { issueText } from '../businessContextPresentation';
import { BusinessContextDetails } from './BusinessContextDetails';
export { issueText } from '../businessContextPresentation';

export function NextEditPreview({ suggestion, onApply, busy = false, autoFocus = false, onCancel, contextSummary, applyLabel }: {
  suggestion: NextEditSuggestion; onApply: () => void; busy?: boolean;
  autoFocus?: boolean; onCancel?: () => void;
  contextSummary?: CompletionContextSummary;
  applyLabel?: string;
}) {
  const preview = useRef<HTMLElement>(null);
  useEffect(() => { if (autoFocus) preview.current?.focus(); }, [autoFocus, suggestion.id]);
  return <section ref={preview} className="next-edit-preview" tabIndex={0} aria-label="本组修改预览"
    onKeyDown={(event) => {
      if (event.nativeEvent.isComposing) return;
      if (event.key === 'Escape' && onCancel) { event.preventDefault(); event.stopPropagation(); onCancel(); return; }
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        if (suggestion.applicable && !busy) onApply();
      }
    }}>
    <h3>{suggestion.label}</h3>
    <p>只修改工作簿，不同步项目。确认前请核对数量、用途与供货变化。</p>
    {suggestion.patches.map((patch) => <div className="change" key={`${patch.sheet}:${patch.row}:${patch.column}`}>
      <strong>{patch.sheet} · {patch.row} 行 · {patch.field}</strong>
      <div className="change-values"><span>{patch.before || '空白'}</span><span>→ {patch.after || '清空'}</span></div>
    </div>)}
    {suggestion.changes.filter((c) => c.kind !== 'devices').map((change) =>
      <details className="change" key={`${change.kind}:${change.id}`}><summary>{change.kind} · {change.id}</summary>
        <pre>{JSON.stringify({ before: change.before, after: change.after }, null, 2)}</pre>
      </details>)}
    <details><summary>业务理由与固定版本证据</summary><pre>{JSON.stringify(suggestion.evidence, null, 2)}</pre></details>
    <BusinessContextDetails summary={contextSummary} />
    {suggestion.issues.map((issue, i) => <div className="issue" key={i}>{issueText(issue)}</div>)}
    <button className="primary" disabled={busy || !suggestion.applicable} onClick={onApply}>{applyLabel ?? '确认应用本组修改'}</button>
    {onCancel && <button type="button" disabled={busy} onClick={onCancel}>返回补全，不应用</button>}
  </section>;
}
