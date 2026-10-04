// Browser-only component harness. No WPS host, network requests, or workbook writes.
import { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { NextEditNotice } from '../src/components/NextEditNotice';
import { nextEditNotice } from '../src/nextEditPresentation';
import { nextEditAction } from '../src/nextEditState';
import { NextEditPreview } from '../src/components/NextEditPreview';
import { businessCompletionSelection, businessCompletionGhost } from '../src/businessCompletion';
import type { ActiveCell } from '../src/types';
import type { NextEditSuggestion } from '../src/businessTypes';
import '../src/inline.css';

const suggestion = { id: 'isolated-fixture', label: '隔离测试：服务器配套预览', patches: [{ sheet: '报价表', row: 8, column: 2,
  field: 'name', before: '', after: '服务器' }], evidence: [{ reason: '测试规则：当前软件缺少服务器配套' }],
  line_bindings: [], changes: [], issues: [], business_operations: [],
  applicable: true, acceptance: 'inline' } as NextEditSuggestion;

function Check() {
  const [query, setQuery] = useState('');
  const [row, setRow] = useState(3);
  const [action, setAction] = useState('尚未按 Tab');
  const [mode, setMode] = useState<'legacy' | 'primary' | 'ambiguous'>('legacy');
  const [preview, setPreview] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const cell = { sheet: '报价表', row, column: 2 } as ActiveCell;
  const notice = nextEditNotice({ suggestion, cell, query });
  return <main style={{ width: 420, padding: 16, fontFamily: 'sans-serif' }}>
    <h2>隔离组件验收 · 非 WPS</h2><p>只验证提示和动作判定，不写工作簿。</p>
    <button onClick={() => { setMode('legacy'); setQuery(''); setRow(3); setAction('尚未按 Tab'); }}>异行建议</button>
    <button onClick={() => { setMode('legacy'); setQuery('务器'); setRow(8); setAction('尚未按 Tab'); }}>非前缀唯一候选</button>
    <button onClick={() => { setMode('primary'); setQuery('服'); setRow(8); }}>主建议与其他候选</button>
    <button onClick={() => { setMode('ambiguous'); setQuery('服'); setRow(8); }}>同型号多配置</button>
    <button onClick={() => setPreview(true)}>打开成组预览</button>
    <button onClick={() => {
      const result = { items: [{ ...suggestion, id: 'alternative' }, suggestion],
        primary_suggestion_id: suggestion.id, decision: { status: 'ready' as const } };
      const selection = businessCompletionSelection({ result: result as never, cell: { ...cell, row: 8 }, query: '服' });
      const ghost = businessCompletionGhost({ result: result as never, index: selection.index,
        cell: { ...cell, row: 8 }, query: '服', ready: true, explicit: false });
      setAction(`主建议位置 ${selection.index + 1}，灰字 ${ghost?.suffix}`);
    }}>主建议不是第一项</button>
    <input ref={input} aria-label="测试输入" value={query} onChange={(e) => setQuery(e.target.value)}
      onKeyDown={(e) => { if (e.key !== 'Tab') return; e.preventDefault();
        setAction(nextEditAction({ suggestion, cell, query, ready: true, composing: false, explicit: false,
          count: mode === 'legacy' ? 1 : 2,
          primarySuggestionId: mode === 'primary' ? suggestion.id : null,
          decision: mode === 'legacy' ? undefined : {
            status: mode === 'primary' ? 'ready' : 'choice_required', reason_code: 'test-only' } }));
      }} />
    <NextEditNotice notice={notice} />
    {preview && <NextEditPreview suggestion={suggestion} autoFocus
      onCancel={() => { setPreview(false); setAction('取消预览，未应用'); input.current?.focus(); }}
      onApply={() => { setPreview(false); setAction('确认回调已触发'); }} />}
    <p role="status">本次动作：{action}；实际工作簿写入：0（未连接宿主）</p>
  </main>;
}

const root = createRoot(document.getElementById('root')!);
root.render(<Check />);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());
