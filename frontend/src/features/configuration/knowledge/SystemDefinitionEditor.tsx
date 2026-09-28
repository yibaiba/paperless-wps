import { Button, Checkbox, Form, Input, Modal, Select, Space } from "antd";
import type { SystemDefinition } from "../types";
import { AuthorFields, required } from "../shared";
import { useDefinitions } from "./useDefinitions";

export function SystemDefinitionEditor({ initial, busy, onSave, onClose }: {
  initial?: SystemDefinition; busy: boolean; onSave: (value: unknown) => void; onClose: () => void;
}) {
  const [form] = Form.useForm();
  const definitions = useDefinitions();
  return <Modal open title="系统版本与角色定义" width={880} onCancel={onClose} onOk={() => form.submit()} confirmLoading={busy}>
    <Form form={form} layout="vertical" initialValues={initial ?? { status: "draft", legacy_names: [], roles: [] }}
      onFinish={(values) => onSave(values)}>
      <Form.Item name="name" label="具体系统版本" rules={required}><Input /></Form.Item>
      <Form.Item name="status" label="角色定义状态"><Select options={[{ value: "draft", label: "待核对" }, { value: "confirmed", label: "已核对角色定义" }]} /></Form.Item>
      <Form.Item name="legacy_names" label="明确对应的旧名称" extra="仅填写已经核实属于同一版本的名称，不按相似名称自动合并。"><Select mode="tags" /></Form.Item>
      <Form.List name="roles">{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: "100%" }}>
        {fields.map((field) => <div key={field.key}>
          <Form.Item name={[field.name, "id"]} hidden><Input /></Form.Item>
          <Space wrap align="start">
            <Form.Item name={[field.name, "name"]} label="角色名称" rules={required}><Input /></Form.Item>
            <Form.Item name={[field.name, "required"]} valuePropName="checked" label="是否必要"><Checkbox>必要角色</Checkbox></Form.Item>
            <Form.Item name={[field.name, "feature"]} label="由选中功能启用（留空为基础角色）"><Input /></Form.Item>
            <Button onClick={() => remove(field.name)}>移除角色</Button>
          </Space>
          <Form.Item name={[field.name, "capability_ids"]} label="所需能力"><Select mode="multiple" options={definitions.data?.capabilities.map((c) => ({ value: c.id, label: c.name }))} /></Form.Item>
          <Form.Item name={[field.name, "inspection_profile"]} label="复用用途检查（固定修订）" getValueProps={(value) => ({ value: value ? `${value.id}@${value.revision}` : undefined })} getValueFromEvent={(value) => { if (!value) return null; const [id, revision] = value.split('@'); return { id, revision: Number(revision) }; }}>
            <Select allowClear options={[...(initial?.inspection_profiles ?? []), ...(definitions.data?.inspection_profiles ?? [])].filter((p, index, all) => all.findIndex((v) => v.id === p.id && v.revision === p.revision) === index).map((p) => ({ value: `${p.id}@${p.revision}`, label: `${p.name} · v${p.revision} · ${p.status === 'confirmed' ? '已确认' : '待核对/停用'}` }))} />
          </Form.Item>
        </div>)}
        <Button onClick={() => add({ id: crypto.randomUUID(), name: "", required: true, feature: "", capability_ids: [] })}>增加角色</Button>
      </Space>}</Form.List>
      <AuthorFields />
    </Form>
  </Modal>;
}
