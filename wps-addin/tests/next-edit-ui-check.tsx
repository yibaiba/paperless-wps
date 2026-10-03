// Browser-only component harness. No WPS host, network requests, or workbook writes.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { NextEditNotice } from '../src/components/NextEditNotice';
import { nextEditNotice } from '../src/nextEditPresentation';
import { nextEditAction } from '../src/nextEditState';
import type { ActiveCell } from '../src/types';
import type { NextEditSuggestion } from '../src/businessTypes';
import '../src/inline.css';

const suggestion = { id: 'isolated-fixture', patches: [{ sheet: '报价表', row: 8, column: 2,
  field: 'name', before: '', after: '服务器' }], evidence: [{ reason: '测试规则：当前软件缺少服务器配套' }],
  applicable: true, acceptance: 'inline' } as NextEditSuggestion;

function Check() {
  const [query, setQuery] = useState('');
  const [row, setRow] = useState(3);
  const [action, setAction] = useState('尚未按 Tab');
  const [mode, setMode] = useState<'legacy' | 'primary' | 'ambiguous'>('legacy');
  const cell = { sheet: '报价表', row, column: 2 } as ActiveCell;
  const notice = nextEditNotice({ suggestion, cell, query });
  return <main style={{ width: 420, padding: 16, fontFamily: 'sans-serif' }}>
    <h2>隔离组件验收 · 非 WPS</h2><p>只验证提示和动作判定，不写工作簿。</p>
    <button onClick={() => { setMode('legacy'); setQuery(''); setRow(3); setAction('尚未按 Tab'); }}>异行建议</button>
    <button onClick={() => { setMode('legacy'); setQuery('务器'); setRow(8); setAction('尚未按 Tab'); }}>非前缀唯一候选</button>
    <button onClick={() => { setMode('primary'); setQuery('服'); setRow(8); }}>主建议与其他候选</button>
    <button onClick={() => { setMode('ambiguous'); setQuery('服'); setRow(8); }}>同型号多配置</button>
    <input aria-label="测试输入" value={query} onChange={(e) => setQuery(e.target.value)}
      onKeyDown={(e) => { if (e.key !== 'Tab') return; e.preventDefault();
        setAction(nextEditAction({ suggestion, cell, query, ready: true, composing: false, explicit: false,
          count: mode === 'legacy' ? 1 : 2,
          primarySuggestionId: mode === 'primary' ? suggestion.id : null,
          decision: mode === 'legacy' ? undefined : {
            status: mode === 'primary' ? 'ready' : 'choice_required', reason_code: 'test-only' } }));
      }} />
    <NextEditNotice notice={notice} />
    <p role="status">本次动作：{action}；实际工作簿写入：0（未连接宿主）</p>
  </main>;
}

createRoot(document.getElementById('root')!).render(<Check />);
