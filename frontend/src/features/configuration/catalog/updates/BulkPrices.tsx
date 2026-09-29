import { useState } from 'react';
import { Alert, Form, Input, InputNumber, Modal, Select, Table } from 'antd';
import { api } from '../../../../shared/api';
import { AuthorFields, required, useVariants } from '../../shared';
import { beijingDate, priceColumns, updateRoot, type Batch, type UpdateRow } from './types';
export function BulkPrices({ batch, rows, onClose, onSaved }: { batch: Batch; rows: UpdateRow[]; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm(); const variants = useVariants();
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState<{ body: string; key: string }>();
  const mode = Form.useWatch('mode', form) ?? 'excel';
  return <Modal open title="批量核对价格" width={850} confirmLoading={busy} onCancel={onClose} okText="保存所选行结论" onOk={() => form.submit()}>
    <Alert type="info" title="逐行明确配置归属；此次仅保存草稿，之后仍需预览发布" description="新表空白或非数值价格保留待核对，不覆盖旧价。规格或备注变化请在单行编辑里处理。" />
    {error ? <Alert type="error" title={error} /> : null}
    <Form form={form} layout="vertical" initialValues={{ column: priceColumns[0], effective_date: beijingDate(), mode: 'excel', actor: batch.actor, evidence: batch.evidence,
      mapping: Object.fromEntries(rows.map(r => [r.id, r.decision?.variant_id || r.variant_id || undefined])) }} onFinish={async values => {
      setBusy(true); setError('');
      try {
        const edits = rows.map(row => {
          const variant = variants.data?.find(v => v.id === values.mapping[row.id]);
          if (!variant) throw new Error('请为每行明确选择配置');
          const raw = values.mode === 'excel' ? row.source?.prices[values.column]?.trim() : values.amount;
          const valid = raw != null && /^\d+(\.\d+)?$/.test(String(raw));
          return { row_id: row.id, decision: { action: 'prices', variant_id: variant.id, expected_variant_revision: variant.revision,
            actor: values.actor, evidence: values.evidence, prices: [{ column: values.column, effective_date: values.effective_date,
              state: values.mode === 'inquiry' ? 'inquiry' : valid ? 'amount' : 'keep', amount: values.mode !== 'inquiry' && valid ? String(raw) : null }] } };
        });
        const body = JSON.stringify({ expected_revision: batch.revision, edits });
        const key = receipt?.body === body ? receipt.key : crypto.randomUUID(); setReceipt({ body, key });
        await api(updateRoot + '/' + batch.id, { method: 'PATCH', body: JSON.stringify({ ...JSON.parse(body), operation_id: key }) }); onSaved(); onClose();
      } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
    }}>
      <Form.Item name="column" label="价格列" rules={required}><Select options={priceColumns.map(c => ({ value: c, label: c }))} /></Form.Item>
      <Form.Item name="mode" label="价格内容"><Select options={[{ value: 'excel', label: '从各行新版 Excel 读取金额' }, { value: 'amount', label: '为所选配置填写共同金额' }, { value: 'inquiry', label: '全部改为待询价' }]} /></Form.Item>
      {mode === 'amount' ? <Form.Item name="amount" label="共同金额" rules={required}><InputNumber stringMode min="0" /></Form.Item> : null}
      <Form.Item name="effective_date" label="生效日期（北京时间）" rules={required}><Input type="date" /></Form.Item>
      <Table size="small" rowKey="id" pagination={false} dataSource={rows} columns={[
        { title: '原始行 / 配置', render: (_, r) => r.source ? `${r.source.model} · ${r.source.sheet} 第 ${r.source.row} 行` : variants.data?.find(v => v.id === r.variant_id)?.name },
        { title: '确认归属', render: (_, r) => <Form.Item name={['mapping', r.id]} rules={required} style={{ margin: 0 }}><Select showSearch optionFilterProp="label" style={{ width: 320 }} options={variants.data?.map(v => ({ value: v.id, label: `${v.product.model} · ${v.name}` }))} /></Form.Item> },
      ]} />
      <AuthorFields />
    </Form>
  </Modal>;
}
