import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
} from "antd";
import type { Configuration, Deployment, Requirement } from "./types";
import { SystemTypeInput } from "./SystemTypeInput";
import { RoleInput } from "./RoleInput";
import {
  AttributeEditor,
  AuthorFields,
  cleanAttributes,
  required,
  units,
} from "./shared";
export function SystemForm({
  configuration,
  onApply,
  onClose,
}: {
  configuration: Configuration;
  onApply: (c: Configuration) => void;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  return (
    <Modal
      open
      title="添加房间与系统"
      onCancel={onClose}
      onOk={() => form.submit()}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(v) => {
          const old = configuration.rooms.find((r) => r.name === v.room);
          const room = old ?? { id: crypto.randomUUID(), name: v.room };
          onApply({
            ...configuration,
            rooms: old ? configuration.rooms : [...configuration.rooms, room],
            systems: [
              ...configuration.systems,
              {
                id: crypto.randomUUID(),
                room_id: room.id,
                name: v.name,
                kind: v.kind,
              },
            ],
          });
          onClose();
        }}
      >
        <Form.Item name="room" label="房间名称" rules={required}>
          <Input placeholder="一楼会议室" />
        </Form.Item>
        <Form.Item name="name" label="系统名称" rules={required}>
          <Input placeholder="一楼无纸化" />
        </Form.Item>
        <Form.Item
          name="kind"
          label="系统 / 方案版本"
          rules={required}
          extra="选择具体版本；Windows、麒麟等运行环境在角色需求中填写。"
        >
          <SystemTypeInput />
        </Form.Item>
      </Form>
    </Modal>
  );
}
export function RequirementForm({
  initial,
  systemId,
  systemName,
  onApply,
  onClose,
}: {
  initial?: Requirement;
  systemId: string;
  systemName: string;
  onApply: (r: Requirement) => void;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  return (
    <Modal
      open
      width={950}
      title="系统需求与运行环境"
      onCancel={onClose}
      onOk={() => form.submit()}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={
          initial ?? { role: "服务端", environment: [], resources: [] }
        }
        onFinish={(v) => {
          onApply({
            ...initial,
            ...v,
            id: initial?.id ?? crypto.randomUUID(),
            system_id: systemId,
            device_id: initial?.device_id ?? null,
            environment: cleanAttributes(v.environment),
          });
          onClose();
        }}
      >
        <Form.Item name="role" label="需要的角色" rules={required}>
          <RoleInput system={systemName} />
        </Form.Item>
        <AttributeEditor name="environment" />
        <Form.List name="resources">
          {(fields, { add, remove }) => (
            <Space orientation="vertical">
              {fields.map((f) => (
                <Space key={f.key}>
                  <Form.Item
                    name={[f.name, "key"]}
                    label="占用资源"
                    rules={required}
                  >
                    <Input placeholder="memory / cores / capacity" />
                  </Form.Item>
                  <Form.Item
                    name={[f.name, "amount"]}
                    label="需求量"
                    rules={required}
                  >
                    <InputNumber stringMode min="0" />
                  </Form.Item>
                  <Form.Item
                    name={[f.name, "unit"]}
                    label="单位"
                    rules={required}
                  >
                    <Select
                      style={{ width: 95 }}
                      options={units.map((value) => ({ value, label: value }))}
                    />
                  </Form.Item>
                  <Button onClick={() => remove(f.name)}>移除</Button>
                </Space>
              ))}
              <Button
                onClick={() => add({ key: "memory", amount: "0", unit: "GB" })}
              >
                增加资源需求
              </Button>
            </Space>
          )}
        </Form.List>
      </Form>
    </Modal>
  );
}
export function DeploymentForm({
  device,
  onApply,
  onClose,
  onDelete,
  onClone,
}: {
  device: Deployment;
  onApply: (d: Deployment) => void;
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
        onFinish={(v) => onApply({ ...device, ...v })}
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

export function ProjectAuthor({
  configuration,
  onApply,
  onClose,
}: {
  configuration: Configuration;
  onApply: (c: Configuration) => void;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  return (
    <Modal
      open
      title="项目维护信息"
      onCancel={onClose}
      onOk={() => form.submit()}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={configuration}
        onFinish={(v) => {
          onApply({ ...configuration, actor: v.actor, evidence: v.evidence });
          onClose();
        }}
      >
        <AuthorFields />
      </Form>
    </Modal>
  );
}
