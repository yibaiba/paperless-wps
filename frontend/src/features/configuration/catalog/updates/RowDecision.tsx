import { PriceHistory } from "./PriceHistory";
import { useState } from 'react';
import { Alert, Button, Collapse, Descriptions, Drawer, Form, Input, InputNumber, Select, Space, Table } from 'antd';
import { api } from '../../../../shared/api';
import { AttributeEditor, AuthorFields, cleanAttributes, required, useProducts, useVariants, useKnowledge } from '../../shared';
import type { Attribute } from '../../types';
import { actions, priceDefaults, priceDecisions, defaultAction, priceColumns, variantPayload, type Batch, type Decision, type UpdateRow, updateRoot } from './types';
export function RowDecision({ row, batch, onClose, onSaved }: { row: UpdateRow; batch: Batch; onClose: () => void; onSaved: () => void }) {
  const variants = useVariants(), products = useProducts(), knowledge = useKnowledge();
  const [form] = Form.useForm();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [request, setRequest] = useState<{ content: string; id: string }>();
  const [actionChosen, setActionChosen] = useState(Boolean(row.decision));
  const initialId = row.decision?.variant_id || row.variant_id;
  const variantId = Form.useWatch('variant_id', form) ?? initialId;
  const variant = variants.data?.find(v => v.id === variantId);
  const action = Form.useWatch('action', form) ?? row.decision?.action ?? defaultAction(row.classification);
  const candidate = row.candidates.find(c => c.variant_id === variantId);
  const initial = row.decision ?? { action, variant_id: initialId, actor: batch.actor, evidence: batch.evidence,
    name: variant?.name ?? row.source?.name ?? '', attributes: variant?.attributes ?? [], description: variant?.description ?? '',
    product_id: variant?.product_id, model: row.source?.model ?? '', product_name: row.source?.name ?? '',
    prices: priceDefaults() };
  async function submit(fields: Decision & { name: string; description: string; attributes: Attribute[]; product_id: string; model: string; product_name: string }) {
    setBusy(true); setError('');
    try {
      const { action: chosen, prices, actor, evidence } = fields;
      const decision: Decision = { action: chosen, variant_id: variantId || '', expected_variant_revision: variant?.revision ?? 0, actor, evidence, manual_unit: fields.manual_unit ?? "", manual_specification: fields.manual_specification ?? "",
        prices: priceDecisions(prices) };
      if (['display', 'correct', 'new_variant', 'new_product'].includes(chosen)) decision.variant = { ...variantPayload(variant), product_id: chosen === 'new_product' ? 'new' : (fields.product_id || variant?.product_id), name: fields.name,
        description: fields.description ?? '', attributes: cleanAttributes(fields.attributes ?? []), actor, evidence };
      if (chosen === 'new_product') decision.product = { name: fields.product_name, model: fields.model, actor, evidence };
      if (["new_variant", "new_product"].includes(chosen)) decision.copy_rule_ids = fields.copy_rule_ids ?? [];
      if (chosen === 'supply') { decision.supply_status = fields.supply_status; decision.replacements = fields.replacements ?? []; }
      const content = JSON.stringify({ expected_revision: batch.revision, edits: [{ row_id: row.id, decision }] });
      const id = request?.content === content ? request.id : crypto.randomUUID(); setRequest({ content, id });
      await api(updateRoot + '/' + batch.id, { method: 'PATCH', body: JSON.stringify({ ...JSON.parse(content), operation_id: id }) });
      onSaved(); onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <Drawer open size={1050} title="核对产品归属与价格" onClose={onClose} extra={<Button type="primary" loading={busy} onClick={() => form.submit()}>保存本行结论</Button>}>
    {error ? <Alert type="error" title={error} /> : null}
    <Form form={form} layout="vertical" initialValues={{ ...initial, ...(row.decision?.variant ?? {}), prices: priceDefaults(row.decision?.prices), model: row.decision?.product?.model ?? row.source?.model ?? "", product_name: row.decision?.product?.name ?? row.source?.name ?? "", actor: initial.actor, evidence: initial.evidence }} onFinish={submit}>
      <Space align="start" style={{ width: '100%' }}>
        <div style={{ width: 320 }}>
          <Descriptions column={1} title="原始来源" size="small" items={[
            { key: 'model', label: '型号', children: row.source?.model ?? variant?.product.model },
            { key: 'cell', label: '位置', children: row.source ? `${row.source.sheet} 第 ${row.source.row} 行` : '人工变更' },
            { key: 'spec', label: '规格', children: row.source?.specification || '见现有配置' },
            { key: 'note', label: '备注', children: row.source?.note || '未填写' },
          ]} />
          {candidate ? <Table size="small" pagination={false} rowKey="field" dataSource={candidate.differences} columns={[
            { title: '变化字段', dataIndex: 'field', render: value => ({ name: '名称', prices: '价格', specification: '规格', note: '备注', unit: '单位', brand: '品牌', category: '分类', short_specification: '简短参数', tender_specification: '招标参数', model: '型号' } as Record<string, string>)[value] ?? value },
            { title: '原值', dataIndex: 'before', render: value => typeof value === 'object' ? JSON.stringify(value) : String(value ?? '') },
            { title: '新值', dataIndex: 'after', render: value => typeof value === 'object' ? JSON.stringify(value) : String(value ?? '') },
          ]} /> : null}
          {candidate?.baseline_conflict ? <Alert type="warning" title="存在多个历史来源，请逐一核对，不自动选择某个来源覆盖" /> : null}
          <Collapse items={candidate?.baselines.map(b => ({ key: b.source.id, label: `${b.source.sheet} 第 ${b.source.row} 行`, children: <div style={{ whiteSpace: 'pre-wrap' }}>{b.source.specification}<p>{b.source.note}</p><pre>{JSON.stringify(b.source.prices, null, 2)}</pre></div> }))} />
        </div>
        <div style={{ width: 620 }}>
          <Form.Item name="variant_id" label="明确选择现有配置 / 复制基准"><Select allowClear showSearch optionFilterProp="label" options={variants.data?.map(v => ({ value: v.id, label: `${v.product.model} · ${v.name}` }))} onChange={id => {
            const v = variants.data?.find(i => i.id === id);
            if (!actionChosen) form.setFieldValue('action', defaultAction(row.candidates.find(c => c.variant_id === id)?.classification ?? row.classification));
            form.setFieldsValue({ name: v?.name, description: v?.description ?? '', attributes: v?.attributes ?? [], product_id: v?.product_id });
          }} /></Form.Item>
          <Form.Item name="action" label="处理方式" rules={required}><Select options={actions} onChange={() => setActionChosen(true)} /></Form.Item>
          {['display', 'correct', 'new_variant', 'new_product'].includes(action) ? <>
            <Form.Item name="name" label="配置名称" rules={required}><Input /></Form.Item>
            <Form.Item name="description" label="展示说明 / 修订说明"><Input.TextArea rows={2} /></Form.Item>
            {action !== 'display' ? <>{action !== "new_product" ? <Form.Item name="product_id" label="所属产品"><Select options={products.data?.map(p => ({ value: p.id, label: `${p.model} · ${p.name}` }))} /></Form.Item> : null}<AttributeEditor /></> : null}
            {action === 'new_product' ? <><Form.Item name="model" label="新产品型号" rules={required}><Input /></Form.Item><Form.Item name="product_name" label="新产品名称" rules={required}><Input /></Form.Item></> : null}
          </> : null}
          {['new_variant', 'new_product'].includes(action) ? <Form.Item name="copy_rule_ids" label="复制搭配为待核对草稿（可选）"><Select mode="multiple" showSearch optionFilterProp="label" options={knowledge.data?.map(k => ({ value: k.id, label: k.name }))} /></Form.Item> : null}
          {!row.source && ['new_variant', 'new_product'].includes(action) ? <><Form.Item name="manual_unit" label="人工资料：计量单位（未知可留空）"><Input /></Form.Item><Form.Item name="manual_specification" label="人工资料：完整参数（留空则逐项保留本次录入参数）"><Input.TextArea rows={3} /></Form.Item></> : null}
          {action === 'supply' ? <><Form.Item name="supply_status" label="供货状态" rules={required}><Select options={[{ value: 'available', label: '可选用' }, { value: 'discontinued', label: '已停产' }, { value: 'not_for_sale', label: '停止销售' }]} /></Form.Item>
            <Form.Item name="replacements" label="人工登记替代候选（不代表兼容）"><Select mode="multiple" options={variants.data?.filter(v => v.id !== variantId).map(v => ({ value: v.id, label: `${v.product.model} · ${v.name}` }))} /></Form.Item></> : null}
          <Alert type="info" title="所有价格默认保留，选择要发布的列。空白不等于零价，待询价会停止沿用旧价。" />
          <Table size="small" pagination={false} dataSource={priceColumns.map((column, index) => ({ column, index }))} rowKey="column" columns={[
            { title: '价格列 / 新表原值', dataIndex: 'column', render: c => <>{c}<div>{row.source?.prices[c] ?? '空白 / 未提供'}</div></> },
            { title: '处理', render: (_, r) => <Form.Item name={['prices', r.index, 'state']} noStyle><Select style={{ width: 115 }} options={[{ value: 'skip', label: '不处理本列' }, { value: 'keep', label: '待核对，保留旧价' }, { value: 'amount', label: '发布金额' }, { value: 'inquiry', label: '待询价' }]} /></Form.Item> },
            { title: '金额', render: (_, r) => <Form.Item name={['prices', r.index, 'amount']} noStyle><InputNumber stringMode min="0" style={{ width: 115 }} /></Form.Item> },
            { title: '生效日期', render: (_, r) => <Form.Item name={['prices', r.index, 'effective_date']} noStyle><Input type="date" style={{ width: 145 }} /></Form.Item> },
          ]} />
          <Collapse items={[{ key: "prices", label: "已发布价格与生效历史", children: <PriceHistory variantId={variantId} /> }]} />
          <AuthorFields />
        </div>
      </Space>
    </Form>
  </Drawer>;
}
