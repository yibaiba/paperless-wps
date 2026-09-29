import { useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, App, Button, Checkbox, Collapse, Drawer, Form, Input, Modal, Radio, Select, Space, Typography } from 'antd';
import type { Configuration } from '../../types';
import { api } from '../../../../shared/api';
import { AuthorFields, required, ROOT } from '../../shared';
import { useDefinitions } from '../../knowledge/useDefinitions';
import { setupFields, setupPayload, type SetupDescription, type SetupValues } from './setupModel';
import { SetupFields } from './SetupFields';

export function SystemForm({ configuration, onApply, onClose, systemId: editingId }: {
  configuration: Configuration; systemId?: string; onApply: (value: Configuration) => void; onClose: () => void;
}) {
  const [form] = Form.useForm<SetupValues>(), definitions = useDefinitions(configuration.definition_snapshot_id);
  const { message } = App.useApp();
  const [systemId] = useState(() => editingId ?? crypto.randomUUID()), [newRoomId] = useState(() => crypto.randomUUID());
  const previous = configuration.systems.find(s => s.id === systemId);
  const identity = Form.useWatch('definition_id', form), packageId = Form.useWatch('knowledge_package_id', form);
  const features = Form.useWatch('features', form) ?? [], roleIds = Form.useWatch('role_ids', form) ?? [];
  const roomMode = Form.useWatch('room_mode', form);
  const [review, setReview] = useState<{ configuration: Configuration; base: Configuration }>();
  const current = useRef(configuration); current.current = configuration;
  const description = useQuery({ queryKey: ['configuration', 'requirement-description', configuration.definition_snapshot_id, configuration.knowledge_snapshot_id, identity, packageId, features], enabled: !!identity,
    queryFn: () => api<SetupDescription>(ROOT + '/requirement-description', { method: 'POST', body: JSON.stringify({ definition_id: identity, knowledge_package_id: packageId ?? '', definition_snapshot_id: configuration.definition_snapshot_id, knowledge_snapshot_id: configuration.knowledge_snapshot_id, features }) }) });
  const fields = setupFields(description.data, roleIds);
  const ambiguous = fields.some(f => fields.some(other => f.scope === other.scope && f.roleId === other.roleId && f.key === other.key && f.unit !== other.unit));
  const preview = useMutation({ mutationFn: async (values: SetupValues) => {
    const base = configuration;
    const setup = setupPayload({ configuration: base, systemId, roomId: values.room_mode === 'new' ? newRoomId : values.room_id,
      newRoom: values.room_mode === 'new' ? { id: newRoomId, name: values.room_name } : undefined, values, description: description.data!, fields });
    const authored = { ...base, actor: values.actor ?? base.actor, evidence: values.evidence ?? base.evidence };
    const result = await api<{ configuration: Configuration }>(ROOT + '/system-setup-preview', { method: 'POST', body: JSON.stringify({ configuration: authored, setup }) });
    if (JSON.stringify(current.current) !== JSON.stringify(base)) throw new Error('项目草稿已变化，请按当前需求重新预览');
    return { ...result, base };
  }, onSuccess: setReview });
  return <><Drawer open size={820} title={previous ? '系统与需求' : '添加房间、系统与需求'} onClose={onClose} extra={<Button type="primary" disabled={!description.data || description.isFetching || !!description.error || ambiguous} loading={preview.isPending} onClick={() => form.submit()}>预览角色与需求</Button>}>
    {(definitions.error || description.error || preview.error) ? <Alert type="error" title={(definitions.error || description.error || preview.error)?.message} /> : null}
    {ambiguous ? <Alert type="error" title="同一需求字段存在不同单位，请先核对用途检查定义。原有输入未改动。" /> : null}
    <Form form={form} layout="vertical" disabled={preview.isPending} initialValues={{ ...previous, actor: configuration.actor, evidence: configuration.evidence, room_mode: previous?.room_id || configuration.rooms.length ? 'existing' : 'new', role_ids: configuration.requirements.filter(r => r.system_id === systemId).map(r => r.role_id).filter(Boolean), features: previous?.features ?? [], features_confirmed: configuration.generation?.features_confirmed.includes(systemId) ?? false, inputs: {} }} onValuesChange={() => { setReview(undefined); preview.reset(); }} onFinish={values => preview.mutate(values)}>
      <Form.Item name="room_mode" label="房间"><Radio.Group options={[{ value: 'existing', label: '选择已有房间' }, { value: 'new', label: '新建房间（同名也独立）' }]} /></Form.Item>
      {roomMode === 'new' ? <Form.Item name="room_name" label="新房间名称" rules={required}><Input /></Form.Item> : <Form.Item name="room_id" label="已有房间" rules={required}><Select options={configuration.rooms.map(r => ({ value: r.id, label: r.name }))} /></Form.Item>}
      <Form.Item name="name" label="本项目中的系统名称" rules={required}><Input placeholder="例如：一楼无纸化" /></Form.Item>
      <Form.Item name="definition_id" label="系统版本" rules={required}><Select disabled={!!previous?.definition_id} options={definitions.data?.definitions.map(d => ({ value: d.id, label: d.name }))} onChange={() => form.setFieldsValue({ knowledge_package_id: '', role_ids: [], features: [], features_confirmed: false, inputs: {} })} /></Form.Item>
      <Form.Item name="knowledge_package_id" label="采用的配置资料版本" extra="可暂不选择，项目继续提示覆盖不足。已有项目升级需使用资料变更预览。"><Select disabled={!!previous?.knowledge_package_id} allowClear options={definitions.data?.packages.filter(p => p.system_definition_id === identity).map(p => ({ value: p.id, label: `${p.name} · v${p.revision}` }))} onChange={() => form.setFieldsValue({ role_ids: [], features: [], features_confirmed: false, inputs: {} })} /></Form.Item>
      {description.data ? <Alert type="info" title={`角色定义 v${description.data.definition_revision} · ${description.data.definition_status === 'confirmed' ? '已确认' : '必要性待核对'}`} description={description.data.notice} /> : null}
      {description.data?.readiness ? <Collapse items={[{ key: 'gaps', label: '所选资料版本的覆盖缺口', children: [...description.data.readiness.roles, ...description.data.readiness.rules].filter(r => r.missing.length).map(r => <Typography.Paragraph key={r.id}><Typography.Text strong>{r.name}：</Typography.Text>{r.missing.join('；')}</Typography.Paragraph>) }]} /> : null}
      <Form.Item name="features" label="本次需要的功能"><Select mode="multiple" onChange={() => form.setFieldValue('features_confirmed', false)} options={description.data?.features.map(value => ({ value, label: value }))} /></Form.Item>
      {description.data?.features.length ? <Form.Item name="features_confirmed" valuePropName="checked" extra="未勾选时保留待确认，不会将空白视为不需要。"><Checkbox>已确认本次功能选择（未选择表示不需要可选功能）</Checkbox></Form.Item> : null}
      <Button onClick={() => form.setFieldValue('role_ids', [...new Set([...roleIds, ...(description.data?.roles.filter(r => r.necessary).map(r => r.id) ?? [])])])}>加入已确认的必要角色建议</Button>
      <Form.Item name="role_ids" label="本次建立或补充的角色" extra="只建立需求，不加入设备。已有角色即使取消选择也不会自动删除。"><Select mode="multiple" options={description.data?.roles.map(r => ({ value: r.id, label: `${r.name} · ${r.necessary ? '必需' : description.data.definition_status === 'draft' ? '必要性待核对' : r.active ? '可选' : '功能未启用'}` }))} /></Form.Item>
      {previous ? <Typography.Paragraph type="secondary">调整功能会保留已有需求与设备；可在预览中核对，移除请使用项目中的明确删除操作。</Typography.Paragraph> : null}
      <SetupFields fields={fields} configuration={configuration} systemId={systemId} description={description.data} />
      {!configuration.actor.trim() || !configuration.evidence.trim() ? <><Typography.Paragraph>首次建立需求，请记录本次整理人及需求来源。</Typography.Paragraph><AuthorFields /></> : null}
    </Form>
  </Drawer>{review ? <Modal open title="确认本次需求变更" onCancel={() => setReview(undefined)} onOk={() => {
    if (JSON.stringify(current.current) !== JSON.stringify(review.base)) { message.error('项目草稿已变化，请重新预览本次需求变更'); setReview(undefined); return; }
    onApply(review.configuration); onClose();
  }} okText="确认应用到草稿">
    <Space orientation="vertical"><Typography.Text>系统：{review.configuration.systems.find(s => s.id === systemId)?.name}</Typography.Text>
      <Typography.Text>新增角色：{review.configuration.requirements.filter(r => !review.base.requirements.some(old => old.id === r.id)).map(r => r.role).join('、') || '无；复用已有角色'}</Typography.Text>
      <Typography.Text>保留已有设备 {review.base.devices.length} 项，不增加采购。</Typography.Text>
      {description.data?.roles.filter(r => !r.active && review.configuration.requirements.some(q => q.system_id === systemId && q.role_id === r.id)).map(r => <Alert key={r.id} type="warning" title={`${r.name} 对应功能未启用；已保留需求及关联设备，请核对`} />)}
    </Space>
  </Modal> : null}</>;
}
