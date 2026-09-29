import { Alert, Form, Input, Select } from 'antd';
import { useDefinitions } from './useDefinitions';

export function QuickIdentity() {
  const form = Form.useFormInstance(), definitions = useDefinitions();
  const definitionId = Form.useWatch('system_definition_id', form);
  const definition = definitions.data?.definitions.find(d => d.id === definitionId);
  return <>
    {definitions.error ? <Alert type="error" title={definitions.error.message} /> : null}
    <Form.Item name="system_definition_id" label="系统版本定义"><Select allowClear options={definitions.data?.definitions.map(d => ({ value: d.id, label: d.name }))}
      onChange={id => form.setFieldsValue({ system_definition_id: id ?? '', role_id: '', role: '', system: definitions.data?.definitions.find(d => d.id === id)?.name ?? '' })} /></Form.Item>
    {definition ? <Form.Item name="role_id" label="承担角色" rules={[{ required: true }]}><Select options={definition.roles.map(r => ({ value: r.id, label: r.name }))}
      onChange={id => form.setFieldValue('role', definition.roles.find(r => r.id === id)?.name ?? '')} /></Form.Item> : null}
    <Form.Item name="system" label={definition ? '系统名称' : '历史系统名称（保留原关联）'} rules={[{ required: true }]}><Input readOnly={!!definition} /></Form.Item>
    <Form.Item name="role" label={definition ? '角色名称' : '历史角色名称（保留原关联）'} rules={[{ required: true }]}><Input readOnly={!!definition} /></Form.Item>
  </>;
}
