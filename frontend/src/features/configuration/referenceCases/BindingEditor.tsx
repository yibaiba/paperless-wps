import { useQuery } from '@tanstack/react-query';
import { api } from '../../../shared/api';
import { ROOT } from '../shared';
import type { SetupDescription } from '../projects/forms/setupModel';
import { Drawer, Form, Input, Select, Button, Alert } from 'antd';
import type { Checked, Configuration } from '../types';
import type { CaseBinding, CaseRow } from './types';
export function BindingEditor({ row, configuration, checked, onClose, onApply }: { row: CaseRow; configuration: Configuration; checked?: Checked; onClose: () => void; onApply: (binding: CaseBinding) => void }) {
  const [form] = Form.useForm(); const disposition = Form.useWatch('disposition', form);
  const systemId = Form.useWatch('feature_system_id', form);
  const system = configuration.systems.find(s => s.id === systemId);
  const description = useQuery({ queryKey: ['configuration', 'requirement-description', configuration.definition_snapshot_id, configuration.knowledge_snapshot_id, system?.definition_id, system?.knowledge_package_id, system?.features], enabled: disposition === 'not_enabled' && !!system?.definition_id,
    queryFn: () => api<SetupDescription>(ROOT + '/requirement-description', { method: 'POST', body: JSON.stringify({ definition_id: system?.definition_id, knowledge_package_id: system?.knowledge_package_id ?? '', definition_snapshot_id: configuration.definition_snapshot_id, knowledge_snapshot_id: configuration.knowledge_snapshot_id, features: system?.features ?? [] }) }) });
  return <Drawer title={`${row.original.section} · ${row.original.name}`} open size={650} onClose={onClose}>
    <Alert type="info" title="这里只建立对照关系，不自动创建、合并、删除或采购设备。" />
    {description.error && <Alert type="error" title={description.error.message} />}
    <Form form={form} layout="vertical" initialValues={row.binding ?? { row_id: row.row_id, device_ids: [], requirement_ids: [], demand_ids: [], included_allocation_ids: [], disposition: 'compare', feature_system_id: '', feature: '', evidence: '' }} onFinish={values => onApply({ ...values, row_id: row.row_id })}>
      <Form.Item name="disposition" label="处理方式"><Select options={[{ value: 'compare', label: '关联实际对象后对账' }, { value: 'not_enabled', label: '本项目明确未启用此功能' }, { value: 'unresolved', label: '保留待确认事项' }]} /></Form.Item>
      <Form.Item name="device_ids" label="实际设备（支持多选，共享设备可对应多行）"><Select mode="multiple" showSearch optionFilterProp="label" options={configuration.devices.map(d => ({ value: d.id, label: `${d.name} · ${d.variant_snapshot?.product.model ?? ''} · ${d.id.slice(-8)}` }))} /></Form.Item>
      <Form.Item name="requirement_ids" label="跟随角色需求"><Select mode="multiple" options={configuration.requirements.map(r => ({ value: r.id, label: `${configuration.systems.find(s => s.id === r.system_id)?.name} / ${r.role}` }))} /></Form.Item>
      <Form.Item name="demand_ids" label="跟随配套需求"><Select mode="multiple" options={checked?.suggestions.map(s => ({ value: s.id, label: `${s.need_name || s.rule.name} · ${s.scope_id ?? s.parent_id}` }))} /></Form.Item>
      <Form.Item name="included_allocation_ids" label="已经明确关联的已含内容"><Select mode="multiple" options={configuration.included_allocations?.map(a => ({ value: a.id, label: `${configuration.devices.find(d => d.id === a.device_id)?.name} · ${a.evidence}` }))} /></Form.Item>
      {disposition === 'not_enabled' && <><Form.Item name="feature_system_id" label="对应系统" rules={[{ required: true }]}><Select options={configuration.systems.map(s => ({ value: s.id, label: s.name }))} /></Form.Item>
        <Form.Item name="feature" label="未启用的功能名称" rules={[{ required: true }]} extra={`此系统目前已启用：${system?.features?.join('、') || '无'}`}><Select loading={description.isFetching} options={description.data?.features.map(value => ({ value, label: description.data?.roles.filter(r => r.feature === value).map(r => r.name).join("、") || value }))} /></Form.Item></>}
      <Form.Item name="evidence" label="采用、替换或待确认的依据" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
      <Button type="primary" htmlType="submit">应用此行映射</Button>
    </Form>
  </Drawer>;
}
