import { Button, Collapse, Form, Input, InputNumber, Select, Space, Typography } from 'antd';
import { EvidenceReferenceFields } from './EvidenceReferenceFields';
import { required, units, useAttributeDefinitions } from '../shared';
import type { SystemDefinition } from '../types';

export function RoleGenerationFields({ index }: { index: number }) {
  const form = Form.useFormInstance();
  const roles = Form.useWatch('roles', { form, preserve: true }) as SystemDefinition['roles'] | undefined;
  const attributes = useAttributeDefinitions();
  const role = roles?.[index];
  const basis = role?.quantity_basis, binding = role?.fulfilled_by;
  const path = (field: string) => [index, field];
  return <Collapse items={[{ key: 'generation', label: '方案生成依据：数量与配套满足', children: <>
    <Form.Item name={path('output_kind')} label="独立计量类型"><Select options={[
      { value: 'hardware', label: '硬件' }, { value: 'software', label: '软件' }, { value: 'license', label: '授权' }, { value: 'accessory', label: '配件' },
    ]} /></Form.Item>
    <Typography.Paragraph type="secondary">直接生成需确认数量。由其他角色配套满足时不再单独生成设备；留空表示依据尚未维护。</Typography.Paragraph>
    {!basis && !binding ? <Space>
      <Button onClick={() => form.setFieldValue(['roles', index, 'quantity_basis'], { status: 'draft', scope: 'system', input_key: '', input_unit: '', mode: null, factor: null, actor: '', evidence: '', evidence_refs: [] })}>维护直接生成数量</Button>
      <Button onClick={() => form.setFieldValue(['roles', index, 'fulfilled_by'], { status: 'draft', role_id: '', need_key: '', actor: '', evidence: '', evidence_refs: [] })}>由其他角色配套满足</Button>
    </Space> : null}
    {basis ? <>
      <Space wrap>
        <Form.Item name={[index, 'quantity_basis', 'scope']} label="数量输入所在范围"><Select style={{ width: 150 }} options={[{ value: 'system', label: '当前系统' }, { value: 'room', label: '当前房间' }, { value: 'project', label: '整个项目' }]} /></Form.Item>
        <Form.Item name={[index, 'quantity_basis', 'mode']} label="计算方式"><Select allowClear style={{ width: 200 }} options={[{ value: 'per_unit', label: '输入数量 × 系数' }, { value: 'per_capacity', label: '按容量向上取整' }, { value: 'per_group', label: '固定数量' }]} /></Form.Item>
        <Form.Item name={[index, 'quantity_basis', 'factor']} label={basis.mode === 'per_group' ? '固定数量' : '系数 / 容量'}><InputNumber stringMode min="0.000001" /></Form.Item>
      </Space>
      {basis.mode !== 'per_group' ? <Space wrap>
        <Form.Item name={[index, 'quantity_basis', 'input_key']} label="规模参数"><Select showSearch style={{ width: 240 }} options={[...(attributes.data ?? []).map(a => ({ value: a.key, label: a.label })), ...(basis.input_key && !attributes.data?.some(a => a.key === basis.input_key) ? [{ value: basis.input_key, label: basis.input_key + '（未注册）' }] : [])]} /></Form.Item>
        <Form.Item name={[index, 'quantity_basis', 'input_unit']} label="输入单位"><Select style={{ width: 140 }} options={[{ value: '', label: '无单位' }, ...units.map(u => ({ value: u, label: u }))]} /></Form.Item>
      </Space> : null}
      <GenerationEvidence index={index} field="quantity_basis" />
      <Button onClick={() => form.setFieldValue(['roles', index, 'quantity_basis'], null)}>清除数量依据，恢复待维护</Button>
    </> : null}
    {binding ? <>
      <Form.Item name={[index, 'fulfilled_by', 'role_id']} label="提供配套的角色" rules={required}><Select options={roles?.filter((_, i) => i !== index).map(r => ({ value: r.id, label: r.name }))} /></Form.Item>
      <Form.Item name={[index, 'fulfilled_by', 'need_key']} label="该角色的配套需求标识" rules={required}><Input placeholder="例如 server；须与已维护的配套需求一致" /></Form.Item>
      <GenerationEvidence index={index} field="fulfilled_by" />
      <Button onClick={() => form.setFieldValue(['roles', index, 'fulfilled_by'], null)}>清除满足关系，恢复待维护</Button>
    </> : null}
  </> }]} />;
}

function GenerationEvidence({ index, field }: { index: number; field: string }) {
  return <>
    <Form.Item name={[index, field, 'status']} label="依据状态"><Select options={[{ value: 'draft', label: '待核对' }, { value: 'confirmed', label: '已确认' }]} /></Form.Item>
    <Form.Item name={[index, field, 'actor']} label="维护人" rules={required}><Input /></Form.Item>
    <Form.Item name={[index, field, 'evidence']} label="数量或满足关系依据" rules={required}><Input.TextArea /></Form.Item>
    <EvidenceReferenceFields name={[index, field, "evidence_refs"]} path={["roles", index, field, "evidence_refs"]} />
  </>;
}
