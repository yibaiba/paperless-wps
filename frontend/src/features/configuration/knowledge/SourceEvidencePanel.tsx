import { WorkbookEvidence } from "../materials/WorkbookEvidence";
import { Button, Collapse, Empty, Form, Space, Tabs, Typography } from 'antd';
import type { Variant } from '../types';

export function SourceEvidencePanel({ variants }: { variants: Variant[] }) {
  const form = Form.useFormInstance();
  const products = !variants.length ? <Empty description="选择产品查看原文" /> : <Collapse items={variants.map(v => ({ key: v.id, label: `${v.product.model} · ${v.name}`, children:
    <Space orientation="vertical" style={{ width: '100%' }}>{v.source_details?.map(source => <div key={source.id}>
      <Typography.Text strong>{source.sheet} · 第 {source.row} 行</Typography.Text>
      {[['规格', source.specification], ['备注', source.note]].filter(([, text]) => text).map(([label, text]) => <div key={label}>
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{text}</Typography.Paragraph>
        <Button size="small" onClick={() => {
          const ref = { source_id: source.id, locator: `${source.sheet} · 第 ${source.row} 行 · ${label}`, quote: text! };
          const previous = form.getFieldValue('evidence_refs') ?? [];
          if (!previous.some((r: typeof ref) => r.source_id === ref.source_id && r.locator === ref.locator && r.quote === ref.quote)) form.setFieldValue('evidence_refs', [...previous, ref]);
        }}>引用这段{label}</Button>
      </div>)}
    </div>)}</Space>,
  }))} />;
  return <Tabs items={[{ key: "products", label: "产品资料", children: products }, { key: "workbook", label: "工作簿说明", children: <WorkbookEvidence onReference={ref => form.setFieldValue("evidence_refs", [...(form.getFieldValue("evidence_refs") ?? []), ref])} /> }]} />;
}
