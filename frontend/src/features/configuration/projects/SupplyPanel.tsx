import { useState } from "react";
import { Alert, Button, Form, Input, InputNumber, Modal, Select, Space, Table, Tag } from "antd";
import type { Configuration, SupplyAllocation } from "../types";
import { required } from "../shared";

const labels = { purchase: "本次采购", existing: "客户已有", unknown: "供货待确认" };
export function SupplyPanel({ configuration, onApply }: {
  configuration: Configuration; onApply: (value: Configuration) => void;
}) {
  const [deviceId, setDeviceId] = useState<string>();
  const device = configuration.devices.find((d) => d.id === deviceId);
  const allocation = configuration.supply_allocations ?? [];
  return <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
    <Alert type="info" showIcon title="部署设备和本次采购分别计量" description="客户已有设备继续参与兼容与容量检查。软件、授权的已有资格须分别填写依据。未分配的数量保留待确认。" />
    <Table rowKey="id" dataSource={configuration.devices} columns={[
      { title: "部署设备", dataIndex: "name" }, { title: "需要数量", dataIndex: "quantity" },
      { title: "供货分配", render: (_, d) => allocation.filter((a) => a.device_id === d.id).map((a) => <Tag key={a.id}>{labels[a.source]} {a.quantity}</Tag>) },
      { title: "操作", render: (_, d) => <Button onClick={() => setDeviceId(d.id)}>分配已有与采购</Button> },
    ]} />
    {device ? <SupplyEditor key={device.id} deviceId={device.id} name={device.name}
      initial={allocation.filter((a) => a.device_id === device.id)}
      onClose={() => setDeviceId(undefined)} onSave={(items) => {
        onApply({ ...configuration, supply_allocations: [...allocation.filter((a) => a.device_id !== device.id), ...items] });
        setDeviceId(undefined);
      }} /> : null}
  </Space>;
}
export function SupplyEditor({ deviceId, name, initial, onSave, onClose }: {
  deviceId: string; name: string; initial: SupplyAllocation[];
  onSave: (items: SupplyAllocation[]) => void; onClose: () => void;
}) {
  const [form] = Form.useForm();
  return <Modal open title={`${name} · 供货分配`} width={800} onCancel={onClose} onOk={() => form.submit()}>
    <Form form={form} layout="vertical" initialValues={{ items: initial }} onFinish={({ items }) => onSave(items)}>
      <Form.List name="items">{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: "100%" }}>
        {fields.map((field) => <div key={field.key}>
          <Form.Item name={[field.name, "id"]} hidden><Input /></Form.Item>
          <Form.Item name={[field.name, "device_id"]} hidden><Input /></Form.Item>
          <Space align="start">
            <Form.Item name={[field.name, "source"]} label="来源"><Select style={{ width: 180 }} options={Object.entries(labels).map(([value, label]) => ({ value, label }))} /></Form.Item>
            <Form.Item name={[field.name, "quantity"]} label="数量" rules={required}><InputNumber stringMode /></Form.Item>
            <Button onClick={() => remove(field.name)}>移除分配</Button>
          </Space>
          <Form.Item name={[field.name, "evidence"]} label="供货或授权依据" rules={required}><Input.TextArea /></Form.Item>
        </div>)}
        <Button onClick={() => add({ id: crypto.randomUUID(), device_id: deviceId, quantity: "", source: "unknown", evidence: "" })}>增加供货分配</Button>
      </Space>}</Form.List>
    </Form>
  </Modal>;
}
