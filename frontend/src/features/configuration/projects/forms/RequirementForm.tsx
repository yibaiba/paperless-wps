import { AutoComplete, Button, Form, Input, InputNumber, Modal, Select, Space, Typography } from "antd";
import type { FormInstance } from "antd";
import type { Deployment, Requirement } from "../../types";
import { RoleInput } from "../../RoleInput";
import { AttributeEditor, cleanAttributes, required, units, useAttributeDefinitions } from "../../shared";

import { useDefinitions } from "../../knowledge/useDefinitions";

import { selectedDefinition } from "../definitionSelection";

export function RequirementForm({
  initial,
  devices,
  systemId,
  systemName,
  definitionId,
  definitionSnapshotId,
  knowledgePackageId,
  requestedRole,
  onApply,
  onClose,
}: {
  initial?: Requirement;
  devices: Deployment[];
  systemId: string;
  systemName: string;
  definitionId?: string;
  definitionSnapshotId?: string | null;
  knowledgePackageId?: string;
  requestedRole?: { id: string; name: string };
  onApply: (requirement: Requirement) => void;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const definitions = useDefinitions(definitionSnapshotId);
  const definition = selectedDefinition({ definition_id: definitionId, knowledge_package_id: knowledgePackageId }, definitions.data);
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
        initialValues={initial ?? { role: requestedRole?.name ?? "服务端", role_id: requestedRole?.id, environment: [], resources: [] }}
        onFinish={() => {
          // Form.List submissions omit unregistered fields; keep the current row values intact.
          const values = form.getFieldsValue(true);
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
        {definition ? <Form.Item name="role_id" label="系统定义中的角色"><Select options={definition.roles.map((r) => ({ value: r.id, label: r.name }))}
          onChange={(id) => form.setFieldValue("role", definition.roles.find((r) => r.id === id)?.name)} /></Form.Item> : null}
        <Form.Item name="role" label="需要的角色" rules={required}>
          <RoleInput system={systemName} />
        </Form.Item>
        <Typography.Paragraph type="secondary">
          房间数、席位数等选择“项目输入”，用于数量或条件计算；操作系统等需要产品满足的条件选择“产品必须满足的参数”。
        </Typography.Paragraph>
        <AttributeEditor name="environment" />
        {initial?.allocations?.length ? <>
          <Typography.Paragraph>本角色由以下设备共同承担。修改分配量不会改变已有设备总量或供货来源。</Typography.Paragraph>
          <Form.List name="allocations">{fields => fields.map(field => {
            const allocation = initial.allocations![field.name];
            return <Space key={field.key} align="start">
              <Typography.Text>{devices.find(d => d.id === allocation.device_id)?.name ?? allocation.device_id}</Typography.Text>
              <Form.Item name={[field.name, "device_id"]} hidden><Input /></Form.Item>
              <Form.Item name={[field.name, "quantity"]} label="承担数量" rules={required}><InputNumber stringMode min="0" /></Form.Item>
              <Form.Item name={[field.name, "evidence"]} label="分配依据" rules={required}><Input /></Form.Item>
            </Space>;
          })}</Form.List>
        </> : null}
        <ResourceFields form={form} />
      </Form>
    </Modal>
  );
}

function ResourceFields({ form }: { form: FormInstance }) {
  const definitions = useAttributeDefinitions();
  const resources = Form.useWatch("resources", form) as Requirement["resources"] | undefined;
  return (
    <Form.List name="resources">
      {(fields, { add, remove }) => (
        <Space orientation="vertical">
          {fields.map((field) => (
            <div className="project-resource-row" key={field.key}>
              <Form.Item name={[field.name, "key"]} label="占用资源" help={resources?.[field.name]?.key && !definitions.data?.some((d) => d.key === resources[field.name].key) ? "未注册字段：按原键匹配，不会自动改写" : undefined} rules={required}>
                <AutoComplete placeholder="选择资源字段；自定义键会保留" options={definitions.data?.filter((d) => ["number", "quantity"].includes(d.kind)).map((d) => ({ value: d.key, label: `${d.label} · ${d.key}` }))} onSelect={(key) => { const definition = definitions.data?.find((d) => d.key === key); if (definition?.units.length === 1) form.setFieldValue(["resources", field.name, "unit"], definition.units[0]); }} />
              </Form.Item>
              <Form.Item name={[field.name, "amount"]} label="需求量" rules={required}>
                <InputNumber stringMode min="0" />
              </Form.Item>
              <Form.Item name={[field.name, "unit"]} label="单位" rules={required}>
                <Select options={units.map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name={[field.name, "aggregation"]} label="多个需求如何合计" rules={required}>
                <Select options={[
                  { value: "sum", label: "需求相加" },
                  { value: "max", label: "取最大需求" },
                ]} />
              </Form.Item>
              <Form.Item name={[field.name, "capacity_basis"]} label="产品容量口径" rules={required}>
                <Select options={[
                  { value: "deployment", label: "本部署的整体容量" },
                  { value: "unit", label: "单台容量 × 实际分配数量" },
                ]} />
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
    aggregation: "sum",
    capacity_basis: "deployment",
  };
}
