import { Button, Form, Input, Select, Space, Typography } from 'antd';
import { ConditionsEditor } from './ConditionsEditor';
import { EvidenceReferenceFields } from './EvidenceReferenceFields';
import { required, useVariants, variantOptions } from '../shared';
import type { SystemDefinition } from '../types';

export function RecommendationFields({ definition }: { definition?: SystemDefinition }) {
  const variants = useVariants();
  return <Form.List name="recommendations">{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: '100%' }}>
    <Typography.Title level={5}>公司推荐顺序</Typography.Title>
    <Typography.Paragraph type="secondary">按选择顺序从优先到备选。推荐不能抵消兼容冲突；已有条件和原文引用会保留。</Typography.Paragraph>
    {fields.map(field => <div key={field.key}>
      <Space wrap>
        <Form.Item name={[field.name, 'role_id']} label="角色" rules={required}><Select style={{ width: 180 }} options={definition?.roles.map(r => ({ value: r.id, label: r.name }))} /></Form.Item>
        <Form.Item name={[field.name, 'need_key']} label="配套需求（角色自身留空）"><Input /></Form.Item>
        <Form.Item name={[field.name, 'status']} label="状态"><Select style={{ width: 150 }} options={[{ value: 'draft', label: '待核对' }, { value: 'confirmed', label: '已确认' }]} /></Form.Item>
        <Button onClick={() => remove(field.name)}>移除推荐</Button>
      </Space>
      <Form.Item name={[field.name, 'variant_ids']} label="配置优先顺序" rules={required}><Select mode="multiple" showSearch optionFilterProp="label" options={variantOptions(variants.data)} /></Form.Item>
      <ConditionsEditor name={[field.name, "conditions"]} path={["recommendations", field.name, "conditions"]} />
      <EvidenceReferenceFields name={[field.name, "evidence_refs"]} path={["recommendations", field.name, "evidence_refs"]} />
      <Form.Item name={[field.name, 'actor']} label="维护人" rules={required}><Input /></Form.Item>
      <Form.Item name={[field.name, 'evidence']} label="推荐依据" rules={required}><Input.TextArea /></Form.Item>
    </div>)}
    <Button disabled={!definition} onClick={() => add({ role_id: '', need_key: '', variant_ids: [], status: 'draft', actor: '', evidence: '', conditions: [], evidence_refs: [] })}>增加推荐顺序</Button>
  </Space>}</Form.List>;
}
