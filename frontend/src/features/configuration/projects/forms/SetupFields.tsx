import { Form, Input, InputNumber, Select, Typography } from 'antd';
import type { Configuration } from '../../types';
import { previousParameter, setupValue, type SetupField, type SetupDescription } from './setupModel';

export function SetupFields({ fields, configuration, systemId, description }: { fields: SetupField[]; configuration: Configuration; systemId: string; description?: SetupDescription }) {
  return <>{fields.map(field => { const previous = previousParameter(field, configuration, systemId); const changedUnit = previous && previous.unit !== field.unit; return <Form.Item key={field.formKey} name={['inputs', field.formKey]} initialValue={setupValue(field, configuration, systemId)}
    label={`${field.label}${field.unit ? `（${field.unit}）` : ''} · ${field.scope === 'system' ? '本系统规模' : description?.roles.find(r => r.id === field.roleId)?.name}`}
    rules={changedUnit ? [{ required: true, message: '请明确填写新单位下的数值，或取消保留原值' }] : []}
    extra={changedUnit ? `原值：${previous.value ?? '未知'} ${previous.unit || '无单位'}，当前单位为 ${field.unit || '无单位'}；不会自动换算。` : field.scope === 'role' ? '只应用到此角色；留空保留未知，不会复制到其他设备。' : '本系统的相关角色复用此输入。'}>
    {field.kind === 'enum' ? <Select mode="tags" placeholder="填写实际环境，可留空" /> : ['number', 'quantity'].includes(field.kind) ? <InputNumber stringMode style={{ width: '100%' }} /> : <Input />}
  </Form.Item>; })}{!fields.length ? <Typography.Paragraph type="secondary">选定角色后显示已登记的需求字段；没有字段不代表资料完整。</Typography.Paragraph> : null}</>;
}
