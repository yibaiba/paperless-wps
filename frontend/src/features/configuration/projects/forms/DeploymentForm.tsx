import { Button, Card, Form, Input, InputNumber, Select, Space } from "antd";
import { useEffect, useState } from "react";
import { NewSupplyDialog, type SupplyChoice } from "../NewSupplyDialog";
import type { Deployment } from "../../types";
import { required } from "../../shared";

export function DeploymentForm({
  device,
  onApply,
  onClose,
  onDelete,
  onClone,
  requiresSupply,
  disabled = false,
}: {
  device: Deployment;
  onApply: (device: Deployment) => void;
  onClose: () => void;
  onDelete: () => void;
  onClone: (supply?: SupplyChoice) => void;
  requiresSupply?: boolean;
  disabled?: boolean;
}) {
  const [form] = Form.useForm();
  useEffect(() => { form.setFieldsValue(device); }, [device, form]);
  const [supplyOpen, setSupplyOpen] = useState(false);
  return (
    <Card
      title="设备属性"
      extra={
        <Button type="text" onClick={onClose}>
          返回候选
        </Button>
      }
    >
      {supplyOpen ? <NewSupplyDialog name={device.name + " 副本"} onClose={() => setSupplyOpen(false)} onConfirm={(supply) => {
        onClone(supply); setSupplyOpen(false);
      }} /> : null}
      <Form
        disabled={disabled}
        form={form}
        layout="vertical"
        initialValues={device}
        onFinish={(values) => onApply({ ...device, ...values })}
      >
        <Form.Item name="name" label="设备名称" rules={required}>
          <Input />
        </Form.Item>
        <Form.Item name="quantity" label="部署总量（供货分配需单独核对）" rules={required}>
          <InputNumber stringMode style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="kind" label="清单类型">
          <Select
            options={[
              { value: "hardware", label: "硬件" },
              { value: "software", label: "软件" },
              { value: "license", label: "授权" },
              { value: "accessory", label: "配件" },
            ]}
          />
        </Form.Item>
        <Form.Item name="note" label="项目备注">
          <Input.TextArea />
        </Form.Item>
        <Space wrap>
          <Button type="primary" htmlType="submit">
            应用属性
          </Button>
          <Button onClick={() => requiresSupply ? setSupplyOpen(true) : onClone()}>复制为新设备</Button>
          <Button danger onClick={onDelete}>
            删除设备及引用
          </Button>
        </Space>
      </Form>
    </Card>
  );
}
