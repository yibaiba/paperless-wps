import { useState } from 'react';
import type { CompletionContextSummary, KnowledgeSummary } from '../businessTypes';
import { issueText } from '../businessContextPresentation';
import './businessContext.css';

const SUPPLY: Record<string, string> = { existing: '已有设备', purchase: '采购', unknown: '供货待确认' };
const PARTICIPATION = { dependency: '参与依赖检查', inventory: '库存候选（不等于可复用）', business_area: '当前业务区' };

export function BusinessContextDetails({ summary }: { summary?: CompletionContextSummary }) {
  const [open, setOpen] = useState(false);
  if (!summary) return <p>本次服务响应未提供上下文摘要，不能据此确认已读取哪些业务行。</p>;
  return <details className="business-context" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>本次读取的上下文 · {summary.rows.length} 个产品 · 本地修订 {summary.local_revision}</summary>
    {open && <>
      <p>{summary.room?.name ?? '未绑定房间'} / {summary.system.name} · {summary.scope.sheet} {summary.scope.start_row}–{summary.scope.end_row} 行</p>
      <p>目录：{summary.catalog_scope.sheet} · 批次 {summary.catalog_scope.import_id}</p>
      <p>未同步业务变化：{summary.local_changes.length} 项。这里只解释临时方案，不保存项目。</p>
      {summary.rows.map((row) => <div className="change" key={row.id}>
        <strong>{row.sheet && row.row ? `${row.sheet} · 第 ${row.row} 行` : '项目基线设备'}：{row.name} × {row.quantity}</strong>
        <p>{PARTICIPATION[row.participation]}；{row.supply_allocations.length
          ? row.supply_allocations.map((a) => `${SUPPLY[a.source] ?? a.source} ${a.quantity}`).join('，') : '供货未确认'}</p>
        <p>{row.uses.length ? row.uses.map((u) => `${u.role}（${u.system_id}）`).join('，') : '用途未关联'}</p>
        <details><summary>行与产品身份</summary><p>{row.line_id ?? '未映射工作簿行'} · 配置 {row.variant_id} · 来源 {row.source_id}</p></details>
      </div>)}
      <details><summary>未同步对象与固定版本</summary><pre>{JSON.stringify({ changes: summary.local_changes, versions: summary.versions }, null, 2)}</pre></details>
      <KnowledgeDetails items={summary.knowledge} />
      {summary.issues.map((issue, i) => <p className="issue" key={i}>{issueText(issue)}</p>)}
    </>}
  </details>;
}

export function KnowledgeDetails({ items }: { items: KnowledgeSummary[] }) {
  const [open, setOpen] = useState(false);
  return <details className="business-context" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>固定知识版本与资料缺口</summary>
    {open && items.map((item) => <div key={item.system_id}>
      <strong>{item.system_name}</strong>
      <p>{item.package ? `${item.package.name} · r${item.package.revision}` : '没有采用已发布的知识包'}</p>
      <p>{item.definition ? `${item.definition.name} · r${item.definition.revision}` : '固定版本中没有系统定义'}</p>
      <p>以下为资料盘点，不等于当前方案检查失败；未启用分支和共享资料不自动阻止独立部署。</p>
      {item.gaps.length ? item.gaps.map((gap, i) => <p className="issue" key={i}>{issueText(gap)}</p>) : <p>资料盘点无缺口；兼容性仍以本次业务检查为准。</p>}
    </div>)}
  </details>;
}
