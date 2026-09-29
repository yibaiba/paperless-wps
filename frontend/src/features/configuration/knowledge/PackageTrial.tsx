import { useState } from 'react';
import { Alert, Button, Collapse, Form, Modal, Select, Space, Table, Typography } from 'antd';
import { useMutation } from '@tanstack/react-query';
import type { Attribute, KnowledgePackage } from '../types';
import { api } from '../../../shared/api';
import { AttributeEditor, cleanAttributes, required, ROOT, useVariants, variantOptions } from '../shared';
import { requiredRoleLabel } from '../projects/definitionSelection';

type Condition = { field: string; operator: string; value: unknown; unit?: string; minimum?: string | null; maximum?: string | null;
  actual?: { value: unknown; unit?: string } | null; result: string };
type Evidence = { id?: string; name: string; revision?: number; evidence: string; result: string;
  effect?: string; activation?: string; activation_conditions?: Condition[]; conditions?: Condition[] };
type Trial = { status: 'pass' | 'conflict' | 'unknown'; notice: string; package_revision: number;
  variant_revision: number; definition_status: string; coverage: { status: string; message: string };
  evidence: Evidence[]; draft_relations: { id: string; name: string; evidence: string }[] };
const resultLabels = { pass: '通过已知适用条件', conflict: '存在明确冲突', unknown: '资料不足，无法确认' };
const showValue = (value: unknown) => value == null ? '未提供' : typeof value === 'string' ? value : JSON.stringify(value);
const conditionLabels: Record<string, string> = { pass: '条件满足', fail: '条件不满足', conflict: '存在冲突', unknown: '资料不足', not_applicable: '未触发' };
const conditionLabel = (value: string) => conditionLabels[value] ?? value;
function expectedValue(condition: Condition) {
  const operatorLabels: Record<string, string> = { eq: '等于', any: '匹配任一', all: '包含全部' };
  const value = condition.operator === 'range'
    ? `${condition.minimum ?? '无下限'} ～ ${condition.maximum ?? '无上限'}`
    : `${operatorLabels[condition.operator] ?? condition.operator} ${showValue(condition.value)}`;
  return `${value} ${condition.unit ?? ''}`.trim();
}

export function PackageTrial({ bundle }: { bundle: KnowledgePackage }) {
  const [open, setOpen] = useState(false);
  return <><Button onClick={() => setOpen(true)}>选型试查</Button>
    {open ? <TrialDialog key={`${bundle.id}:${bundle.revision}`} bundle={bundle} onClose={() => setOpen(false)} /> : null}</>;
}

function TrialDialog({ bundle, onClose }: { bundle: KnowledgePackage; onClose: () => void }) {
  const variants = useVariants(), [form] = Form.useForm();
  const roleId = Form.useWatch('role_id', form);
  const role = bundle.definition.roles.find(r => r.id === roleId);
  const rules = bundle.rules.filter(r => r.kind === 'suitability' && r.status !== 'disabled' &&
    (r.system_definition_id ? r.system_definition_id === bundle.system_definition_id : r.system === bundle.definition.name) &&
    (r.role_id ? r.role_id === roleId : r.role === role?.name));
  const fields = [...new Set(rules.flatMap(r => [...r.conditions, ...(r.activation_conditions ?? [])].map(c => c.field).filter(f => f.startsWith('project.'))))];
  const trial = useMutation({ mutationFn: (values: { role_id: string; variant_id: string; environment: Attribute[] }) =>
    api<Trial>(`${ROOT}/knowledge-packages/${bundle.id}/trial`, { method: 'POST', body: JSON.stringify({
      expected_revision: bundle.revision, ...values, environment: cleanAttributes(values.environment),
    }) }) });
  const result = trial.data;
  return <Modal open title={`${bundle.name} · 选型试查`} width={1000} onCancel={onClose} footer={null}>
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Alert type="info" showIcon title="只读试查，不加入清单，不保存项目，也不确认知识" description="使用包内固定关系和当前产品配置。通过仅表示已知适用条件满足，不能代替整套项目检查。" />
      {variants.error ? <Alert type="error" title={variants.error.message} /> : null}
      <Form form={form} layout="vertical" initialValues={{ environment: [] }} disabled={trial.isPending} onValuesChange={() => trial.reset()} onFinish={values => trial.mutate(values)}>
        <Form.Item name="role_id" label="试查角色" rules={required}><Select options={bundle.definition.roles.map(r => ({ value: r.id, label: `${r.name} · ${requiredRoleLabel(r, bundle.definition.status)}` }))} /></Form.Item>
        <Form.Item name="variant_id" label="试查产品配置" rules={required}><Select showSearch optionFilterProp="label" loading={variants.isPending} options={variantOptions(variants.data)} /></Form.Item>
        <Typography.Paragraph type="secondary">{fields.length ? `本角色关系引用的项目参数：${fields.map(f => f.slice('project.'.length)).join('、')}。按实际需求填写；留空时检查会保留资料缺口。` : '此角色未登记项目参数提示；没有提示不代表资料完整。'}</Typography.Paragraph>
        <AttributeEditor name="environment" />
        <Button type="primary" htmlType="submit" loading={trial.isPending} disabled={!!variants.error}>执行试查</Button>
      </Form>
      {trial.error ? <Alert type="error" title="试查失败" description={trial.error.message} /> : null}
      {result ? <>
        <Alert showIcon type={result.status === 'conflict' ? 'error' : result.status === 'pass' ? 'success' : 'warning'} title={resultLabels[result.status]} description={result.notice} />
        <Typography.Text>知识包 v{result.package_revision} · 当前产品 v{result.variant_revision} · 角色定义{result.definition_status === 'confirmed' ? '已确认' : '仍为草稿'}</Typography.Text>
        <Typography.Paragraph>配套范围：{result.coverage.message}</Typography.Paragraph>
        {result.draft_relations.length ? <Alert type="warning" title={`${result.draft_relations.length} 条草稿适用关系未作为通过依据`} description={result.draft_relations.map(r => r.name).join('；')} /> : null}
        <Collapse items={result.evidence.map((e, index) => ({ key: String(index), label: `${e.name} · ${e.effect === 'deny' ? '禁止关系 · ' : ''}${conditionLabel(e.result)} ${e.revision ? `· v${e.revision}` : ''}`, children: <>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{e.evidence}</Typography.Paragraph>
          {e.activation_conditions?.length ? <Typography.Paragraph>触发条件：{e.activation_conditions.map(c => `${c.field} ${expectedValue(c)}`).join('；')}。{conditionLabel(e.activation ?? 'unknown')}</Typography.Paragraph> : null}
          <Table rowKey={(_, i) => String(i)} pagination={false} size="small" dataSource={e.conditions ?? []} columns={[
            { title: '条件字段', dataIndex: 'field' }, { title: '规则要求', render: (_, c) => expectedValue(c) },
            { title: '本次输入 / 产品值', render: (_, c) => `${showValue(c.actual?.value)} ${c.actual?.unit ?? ''}`.trim() }, { title: '结果', dataIndex: 'result', render: conditionLabel },
          ]} />
        </> }))} />
      </> : null}
    </Space>
  </Modal>;
}
