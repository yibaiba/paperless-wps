import { Button, Card, Form, Input, InputNumber, Select, Space } from "antd";
import type { Deployment } from "../../types";
import { required } from "../../shared";

export function DeploymentForm({
  device,
  onApply,
  onClose,
  onDelete,
  onClone,
}: {
  device: Deployment;
  onApply: (device: Deployment) => void;
  onClose: () => void;
  onDelete: () => void;
  onClone: () => void;
}) {
  const [form] = Form.useForm();
  return (
    <Card
      title="设备属性"
      extra={
        <Button type="text" onClick={onClose}>
          返回候选
        </Button>
      }
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={device}
        onFinish={(values) => onApply({ ...device, ...values })}
      >
        <Form.Item name="name" label="设备名称" rules={required}>
          <Input />
        </Form.Item>
        <Form.Item name="quantity" label="数量" rules={required}>
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
          <Button onClick={onClone}>复制为新设备</Button>
          <Button danger onClick={onDelete}>
            删除设备及引用
          </Button>
        </Space>
      </Form>
    </Card>
  );
}
