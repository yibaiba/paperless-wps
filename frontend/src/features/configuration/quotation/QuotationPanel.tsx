import { PriceUpdates } from "./PriceUpdates";
import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, App, Button, Collapse, Descriptions, Empty, Space, Spin, Typography } from "antd";
import { api } from "../../../shared/api";
import { configurationKeys } from "../queryKeys";
import type { Configuration, ProjectConfiguration } from "../types";
import type { QuotationOutput, QuoteTemplate } from "./types";
import { QuotationForm } from "./QuotationForms";
import './quotation.css';

import type { SheetControls } from "./sheet/QuotationSheet";
import { loadQuotationSheet } from './loadSheet';
import { SheetBoundary } from './SheetBoundary';
const QuotationSheet = lazy(loadQuotationSheet);

interface Artifact { id: string; filename: string; download_path: string }
export function QuotationPanel({ configuration, output, saved, dirty, stale, busy, checking, onApply, onCheck, sheetControls }: {
  configuration: Configuration; output?: QuotationOutput | null; saved: ProjectConfiguration;
  sheetControls: SheetControls;
  dirty: boolean; stale: boolean; busy: boolean; checking: boolean; onApply: (value: Configuration) => void; onCheck: () => void;
}) {
  const [priceUpdates, setPriceUpdates] = useState(false);
  const [editing, setEditing] = useState(false);
  const { message } = App.useApp();
  const template = useQuery({ queryKey: configurationKeys.quoteTemplate, queryFn: () => api<QuoteTemplate>("/quotation-template") });
  const exporting = useMutation({ mutationFn: () => api<{ artifacts: Artifact[] }>("/list-tools/list_export", {
    method: "POST", body: JSON.stringify({ project_id: saved.project_id, revision: saved.revision, output: "both", operation_id: crypto.randomUUID() }),
  }), onError: (e) => message.error(e.message) });
  const quote = configuration.quotation;
  return <Space orientation="vertical" style={{ width: "100%" }} size="middle">
    <Space wrap>
      <Button onClick={() => setEditing(true)} disabled={!template.data || busy}>报价资料与价格列</Button>
      <Button disabled={busy || !quote?.price_column} onClick={() => setPriceUpdates(true)}>检查价格更新</Button>
      <Button onClick={onCheck} disabled={busy} loading={checking}>{stale ? '重新检查并计算报价' : '检查并计算报价'}</Button>
      <Button disabled={busy || dirty || !saved.revision || !saved.configuration.quotation} loading={exporting.isPending} onClick={() => exporting.mutate()}>导出清单和公司报价模板</Button>
    </Space>
    {template.error ? <Alert type="error" title={template.error.message} /> : null}
    {dirty ? <Typography.Text type="secondary">保存后可导出本次修改；文件固定到保存版本。</Typography.Text> : null}
    {stale ? <Alert type="warning" title="报价数据已变化，请重新检查；下方仍为上次计算结果。" /> : null}
    {quote ? <>
      <div className="quotation-summary" aria-label="报价汇总">
        <div><Typography.Text type="secondary">{stale ? '上次报价合计' : '报价合计'}</Typography.Text><strong>{output?.total != null ? `¥ ${output.total}` : '待确认'}</strong></div>
        <div><Typography.Text type="secondary">{stale ? '上次已知金额小计' : '已知金额小计'}</Typography.Text><strong>{output ? `¥ ${output.known_subtotal}` : '请先检查'}</strong></div>
        <div><Typography.Text type="secondary">{stale ? '上次报价问题' : '报价问题'}</Typography.Text><strong>{output ? `${output.issues.length} 项` : '未检查'}</strong></div>
      </div>
      <Collapse size="small" items={[{ key: 'details', label: `${quote.customer || '客户待填写'} · ${quote.price_column || '逐项人工单价'} · 查看报价资料与税运说明`, children: <Descriptions column={2} size="small" items={[
      { key: "customer", label: "客户", children: quote.customer || "未填写" },
      { key: "project", label: "项目", children: quote.project_name || saved.name },
      { key: "price", label: "采用价格", children: quote.price_column || "待指定 / 逐项人工单价" },
      { key: "terms", label: "税运说明", children: quote.tax_terms, span: 2 },
    ]} /> }]} />
    </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先填写报价资料，再选择产品库价格或逐项调价"><Button type="primary" disabled={!template.data || busy} onClick={() => setEditing(true)}>设置本次报价</Button></Empty>}
    <SheetBoundary><Suspense fallback={<Spin description="正在加载报价工作表…" />}><QuotationSheet {...sheetControls} output={output} stale={stale} /></Suspense></SheetBoundary>
    {exporting.data?.artifacts.map((artifact) => <a key={artifact.id} href={artifact.download_path} download>{artifact.filename}</a>)}
    {priceUpdates ? <PriceUpdates context={sheetControls} onClose={() => setPriceUpdates(false)} /> : null}
    {editing && template.data ? <QuotationForm value={quote} template={template.data} projectName={saved.name} onClose={() => setEditing(false)} onApply={(quotation) => onApply({ ...configuration, quotation })} /> : null}
  </Space>;
}
