// Isolated test entry, deliberately absent from Vite's production build inputs.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { NextEditPreview } from '../src/components/NextEditPreview';
import { JournalPanel } from '../src/components/JournalPanel';
import { applyNextEdit } from '../src/editJournal';
import '../src/styles.css';

let metadata = { schema_version: 2, workbook_instance_id: 'browser-fixture', line_bindings: [],
  business: { local_revision: 0, scopes: [], operations: [], recent_edits: [] } };
const cells = new Map([[1, '原型号'], [2, '1']]);
const journals = new Map();
const host = {
  readCell: (cell) => ({ ...cell, value: cells.get(cell.column), formula: '', merged: false }),
  writeCellValue: (cell, value) => cells.set(cell.column, value),
  readMetadata: () => structuredClone(metadata),
  writeMetadata: (value) => { metadata = structuredClone(value); },
  journals: () => [...journals.values()],
  writeJournal: (value) => journals.set(value.operation_id, structuredClone(value)),
};
const suggestion = { id: 'fixture-suggestion', kind: 'business', label: '核对终端容量后的配套调整（测试）',
  patches: [{ sheet: '隔离报价表', row: 5, column: 1, field: 'model', before: '原型号', after: '测试型号' },
    { sheet: '隔离报价表', row: 5, column: 2, field: 'quantity', before: '1', after: '2' }],
  line_bindings: [], business_operations: [], inverse_business_operations: [], changes: [],
  evidence: [{ rule_id: 'isolated-rule', revision: 1, reason: '仅验证预览交互，不构成真实业务依据' }],
  issues: [], applicable: true, acceptance: 'preview', context_fingerprint: 'fixture', local_revision: 0 };

function Harness() {
  const [status, setStatus] = useState('未应用');
  const [, refresh] = useState(0);
  return <main style={{ maxWidth: 420, padding: 16, margin: 20 }}><h1>隔离浏览器验证 · 非 WPS 真机</h1>
    <p>这里使用测试内存宿主，只验证组件、成组修改和独立撤销，不连接生产数据。</p>
    <output aria-label="当前测试单元格">{cells.get(1)} / 数量 {cells.get(2)} / {status}</output>
    <NextEditPreview suggestion={suggestion} onApply={() => {
      try { applyNextEdit({ host, suggestion, operationId: 'browser-operation' }); setStatus('已应用'); }
      catch (reason) { setStatus(String(reason)); }
      refresh((n) => n + 1);
    }} />
    <JournalPanel host={host} onChanged={() => { setStatus('已撤销'); refresh((n) => n + 1); }} />
  </main>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
