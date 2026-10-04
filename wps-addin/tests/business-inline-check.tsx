// Exercises the real editor and journal against an explicitly isolated memory adapter.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BusinessInlineEditor } from '../src/components/BusinessInlineEditor';
import { businessInlineFixture, type Scenario } from './business-inline-fixture';
import type { WpsHostAdapter } from '../src/host';
import '../src/inline.css';

function ScenarioCheck({ scenario }: { scenario: Scenario }) {
  const [, render] = useState(0);
  const [fixture] = useState(() => businessInlineFixture(scenario, () => render((n) => n + 1)));
  return <>
    <div style={{ width: 420, height: fixture.stats.height, marginTop: 12 }}>
      <BusinessInlineEditor host={fixture.host as unknown as WpsHostAdapter} api={fixture.api} />
    </div>
    <button onClick={fixture.release}>返回待处理选择</button>
    {scenario === 'slow-query' && <>
      <button onClick={fixture.switchBeforeReply}>先切换单元格，再返回旧响应</button>
      <button onClick={fixture.refreshContext}>刷新当前单元格会话</button>
    </>}
    <button onClick={fixture.repairRead}>恢复测试读取</button>
    <pre role="status" aria-label="隔离测试结果">{JSON.stringify({ ...fixture.stats,
      journals: [...fixture.journals.values()].map((j) => j.state), cells: [...fixture.values],
      bindings: fixture.host.readMetadata().line_bindings.map((line: { row: number; variant_id: string; source_id: string }) =>
        ({ row: line.row, variant_id: line.variant_id, source_id: line.source_id })) }, null, 2)}</pre>
  </>;
}
function Check() {
  const [scenario, setScenario] = useState<Scenario>('choice');
  const [generation, setGeneration] = useState(0);
  return <main style={{ padding: 16, fontFamily: 'sans-serif', height: '100vh', overflow: 'auto' }}>
    <h2>业务浮层隔离验收 · 非 WPS</h2>
    <p>真实组件与事务代码；测试内存宿主、固定候选。无真实工作簿、服务端或账号请求。</p>
    {(['choice', 'preview', 'off-row', 'off-row-preview', 'refresh-error', 'slow-choice', 'same-name',
      'continuation', 'undo-refresh-error', 'slow-prefetch', 'slow-query'] as const).map((value) =>
      <button key={value} onClick={() => { setScenario(value); setGeneration((n) => n + 1); }}>{value}</button>)}
    <ScenarioCheck key={generation} scenario={scenario} />
  </main>;
}
const root = import.meta.hot?.data.root ?? createRoot(document.getElementById('root')!);
if (import.meta.hot) import.meta.hot.data.root = root;
root.render(<Check />);
