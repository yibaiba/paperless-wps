import { Button, Form, Input, InputNumber, Modal, Select, Space } from "antd";
import type { FormInstance } from "antd";
import type { Requirement } from "../../types";
import { RoleInput } from "../../RoleInput";
import { AttributeEditor, cleanAttributes, required, units } from "../../shared";

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
  onApply: (requirement: Requirement) => void;
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
        initialValues={initial ?? { role: "服务端", environment: [], resources: [] }}
        onFinish={(values) => {
          onApply({
            ...initial,
            ...values,
            id: initial?.id ?? crypto.randomUUID(),
            system_id: systemId,
            device_id: initial?.device_id ?? null,
            environment: cleanAttributes(values.environment),
          });
          onClose();
        }}
      >
        <Form.Item name="role" label="需要的角色" rules={required}>
          <RoleInput system={systemName} />
        </Form.Item>
        <AttributeEditor name="environment" />
        <ResourceFields form={form} />
      </Form>
    </Modal>
  );
}

function ResourceFields({ form }: { form: FormInstance }) {
  return (
    <Form.List name="resources">
      {(fields, { add, remove }) => (
        <Space orientation="vertical">
          {fields.map((field) => (
            <div className="project-resource-row" key={field.key}>
              <Form.Item name={[field.name, "key"]} label="占用资源" rules={required}>
                <Input placeholder="memory / cores / terminal_capacity" />
              </Form.Item>
              <Form.Item name={[field.name, "amount"]} label="需求量" rules={required}>
                <InputNumber stringMode min="0" />
              </Form.Item>
              <Form.Item name={[field.name, "unit"]} label="单位" rules={required}>
                <Select options={units.map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item
                name={[field.name, "applies_to"]}
                label="由谁承担"
                initialValue="selected_device"
              >
                <Select
                  options={[
                    { value: "selected_device", label: "当前选中配置" },
                    { value: "accessory", label: "指定配套设备" },
                  ]}
                  onChange={(value) => clearAccessoryTarget(form, field.name, value)}
                />
              </Form.Item>
              <AccessoryTarget form={form} fieldName={field.name} />
              <Button onClick={() => remove(field.name)}>移除</Button>
            </div>
          ))}
          <Button onClick={() => add(defaultResource())}>增加资源需求</Button>
        </Space>
      )}
    </Form.List>
  );
}

function AccessoryTarget({
  form,
  fieldName,
}: {
  form: FormInstance;
  fieldName: number;
}) {
  return (
    <Form.Item noStyle shouldUpdate>
      {() =>
        form.getFieldValue(["resources", fieldName, "applies_to"]) === "accessory" ? (
          <Form.Item name={[fieldName, "target_need_key"]} label="配套需求标识" rules={required}>
            <Input placeholder="server" />
          </Form.Item>
        ) : null
      }
    </Form.Item>
  );
}

function clearAccessoryTarget(
  form: FormInstance,
  fieldName: number,
  appliesTo: string,
) {
  if (appliesTo === "selected_device") {
    form.setFieldValue(["resources", fieldName, "target_need_key"], "");
  }
}

function defaultResource() {
  return {
    key: "memory",
    amount: "0",
    unit: "GB",
    applies_to: "selected_device",
    target_need_key: "",
  };
}
