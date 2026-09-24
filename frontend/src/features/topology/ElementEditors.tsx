import {Alert, Button, Form, Input, InputNumber, Modal, Select} from 'antd';
import type {Device, Diagram, Relation, SystemGroup} from './types';
import {modeLabels, relationLabels} from './types';

const required = [{required: true, whitespace: true, message: '请填写此项'}];
interface GroupProps {group: SystemGroup; onSave: (group: SystemGroup) => void; onClose: () => void; onDelete?: () => void}
export function GroupEditor({group, onSave, onClose, onDelete}: GroupProps) {
  const [form] = Form.useForm<SystemGroup>();
  return <Modal open title="系统分组" onCancel={onClose} onOk={() => form.submit()} okText="应用到画布" cancelText="取消"
    footer={(_, {OkBtn, CancelBtn}) => <><Button danger disabled={!onDelete} onClick={onDelete}>删除分组，保留设备</Button><CancelBtn/><OkBtn/></>}>
    <Form form={form} layout="vertical" initialValues={group} onFinish={values => onSave({...group, ...values})}>
      <Form.Item name="name" label="系统 / 房间名称" rules={required}><Input placeholder="例如：一楼会议室 · 无纸化"/></Form.Item>
      <Form.Item name="product_line" label="方案对应产品线"><Input placeholder="由你确认，不会改写产品库归属"/></Form.Item>
      <Alert type="info" title="设备通过编辑中的「放置分组」加入此区域；共享设备可放在区域外。"/>
    </Form>
  </Modal>;
}
interface DeviceProps {device: Device; groups: SystemGroup[]; model: string; onSave: (device: Device) => void; onClose: () => void; onDelete: () => void; onDetail: () => void}
export function DeviceEditor({device, groups, model, onSave, onClose, onDelete, onDetail}: DeviceProps) {
  const [form] = Form.useForm<Device>();
  return <Modal open title={`设备配置 · ${model}`} onCancel={onClose} onOk={() => form.submit()} okText="应用到画布" cancelText="取消"
    footer={(_, {OkBtn, CancelBtn}) => <><Button danger onClick={onDelete}>删除设备</Button><Button onClick={onDetail}>查看产品资料</Button><CancelBtn/><OkBtn/></>}>
    <Form form={form} layout="vertical" initialValues={device} onFinish={values => onSave({...device, ...values, group_id: values.group_id ?? null})}>
      <Form.Item name="role" label="在方案中承担的角色"><Input placeholder="例如：无纸化服务器"/></Form.Item>
      <Form.Item name="quantity" label="设备数量" rules={[{required: true}]}><InputNumber stringMode min="0" className="topology-full"/></Form.Item>
      <Form.Item name="group_id" label="放置分组"><Select allowClear placeholder="未分组 / 共享区" options={groups.map(g => ({value: g.id, label: g.name}))}/></Form.Item>
      <Form.Item name="serves_group_ids" label="额外服务系统（共用设备）"><Select mode="multiple" options={groups.map(g => ({value: g.id, label: g.name}))}/></Form.Item>
      <Form.Item name="note" label="适用条件 / 说明"><Input.TextArea rows={3}/></Form.Item>
      <Alert type="info" title="一个节点代表一批相同配置设备。共用设备只添加一次，服务多个系统不会重复计入清单。"/>
    </Form>
  </Modal>;
}
interface RelationProps {relation: Relation; diagram: Diagram; models: Record<string, {model: string}>; onSave: (relation: Relation) => void; onClose: () => void; onDelete?: () => void}
export function RelationEditor({relation, diagram, models, onSave, onClose, onDelete}: RelationProps) {
  const [form] = Form.useForm<Relation>();
  const kind = Form.useWatch('kind', form) ?? relation.kind;
  const nodes = diagram.devices.map((device, index) => ({value: device.id,
    label: `${index + 1}. ${models[device.product_id]?.model ?? device.product_id} · ${device.role || '角色待填'}`}));
  return <Modal open title="设备关系" onCancel={onClose} onOk={() => form.submit()} okText="应用到画布" cancelText="取消"
    footer={(_, {OkBtn, CancelBtn}) => <><Button danger disabled={!onDelete} onClick={onDelete}>删除关系</Button><CancelBtn/><OkBtn/></>}>
    <Form form={form} layout="vertical" initialValues={relation} onFinish={values => onSave({...relation, ...values})}>
      <Form.Item name="source" label="起点设备（触发产品）" rules={required}><Select options={nodes}/></Form.Item>
      <Form.Item name="target" label="终点设备（配套产品）" rules={[...required, {validator: async (_, value) => {
        if (value === form.getFieldValue('source')) throw new Error('请选择不同的设备');
      }}]} dependencies={['source']}><Select options={nodes}/></Form.Item>
      <Form.Item name="kind" label="关系类型"><Select options={Object.entries(relationLabels).map(([value, label]) => ({value, label}))}/></Form.Item>
      {kind === 'required' ? <>
        <Form.Item name="mode" label="数量计算方式"><Select options={Object.entries(modeLabels).map(([value, label]) => ({value, label}))}/></Form.Item>
        <Form.Item name="factor" label="数量 / 容量参数" rules={[{required: true}]}><InputNumber stringMode min="0" className="topology-full"/></Form.Item>
        <Alert className="section-bottom" type="info" title="例如：每件配 2 个填 2；每台可带 50 个填 50；每组至少 1 台填 1。"/>
      </> : null}
      {kind === 'connection' ? <>
        <Form.Item name="source_port" label="起点接口"><Input placeholder="接口类型 / 端口编号 / 协议"/></Form.Item>
        <Form.Item name="target_port" label="终点接口"><Input placeholder="接口类型 / 端口编号 / 协议"/></Form.Item>
        <Form.Item name="cable" label="线材规格"><Input placeholder="填写已确认的线材"/></Form.Item>
        <Form.Item name="length_m" label="实际线路长度（米，可留空）"><InputNumber stringMode min="0" className="topology-full"/></Form.Item>
        <Alert className="section-bottom" type="info" title="接线仅作记录，尚未校验接口兼容性或计入线材清单；画布距离不是实际线长。"/>
      </> : null}
      <Form.Item name="evidence" label="依据 / 适用条件" rules={kind === 'required' ? required : []}>
        <Input.TextArea rows={3} placeholder="产品资料出处、已确认的售前经验或待确认问题"/>
      </Form.Item>
    </Form>
  </Modal>;
}
