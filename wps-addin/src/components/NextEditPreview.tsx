import type { NextEditSuggestion } from '../businessTypes';

export function NextEditPreview({ suggestion, onApply, busy = false }: {
  suggestion: NextEditSuggestion; onApply: () => void; busy?: boolean;
}) {
  return <section className="next-edit-preview" tabIndex={0} aria-label="本组修改预览"
    onKeyDown={(event) => {
      if (event.nativeEvent.isComposing) return;
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
    {suggestion.issues.map((issue, i) => <div className="issue" key={i}>{issueText(issue)}</div>)}
    <button className="primary" disabled={busy || !suggestion.applicable} onClick={onApply}>确认应用本组修改</button>
  </section>;
}

export function issueText(issue: unknown): string {
  if (typeof issue === 'string') return issue;
  if (issue && typeof issue === 'object' && 'message' in issue) return String(issue.message);
  return JSON.stringify(issue);
}
