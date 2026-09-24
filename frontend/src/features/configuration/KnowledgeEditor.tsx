import {
  AutoComplete,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
} from "antd";
import type { Knowledge } from "./types";
import {
  AuthorFields,
  required,
  units,
  useVariants,
  variantOptions,
} from "./shared";

export const emptyKnowledge = {
  name: "",
  kind: "suitability",
  status: "draft",
  effect: "allow",
  selector: {
    variant_ids: [],
    category: "",
    series: [],
    exclude_variant_ids: [],
  },
  system: "",
  role: "",
  conditions: [],
  target_variant_ids: [],
  accessory_type: "required",
  mode: "per_unit",
  factor: "1",
  shared_roles: [],
};
export function ConditionsEditor() {
  const form = Form.useFormInstance();
  const conditions = Form.useWatch("conditions", form) as
    Knowledge["conditions"] | undefined;
  return (
    <Form.List name="conditions">
      {(fields, { add, remove }) => (
        <Space orientation="vertical" style={{ width: "100%" }}>
          {fields.map((field) => (
            <div className="config-field-row" key={field.key}>
              <Form.Item
                name={[field.name, "field"]}
                label="条件字段"
                rules={required}
              >
                <AutoComplete
                  placeholder="选择条件字段"
                  options={[
                    { value: "product.cpu_arch", label: "产品 CPU 架构" },
                    { value: "project.cpu_arch", label: "需求 CPU 架构" },
                    { value: "product.os", label: "产品操作系统" },
                    { value: "project.os", label: "部署操作系统" },
                    { value: "product.memory", label: "产品内存" },
                    { value: "product.capacity", label: "产品容量" },
                    {
                      value: "product.software_version",
                      label: "产品软件版本",
                    },
                    {
                      value: "project.software_version",
                      label: "所需软件版本",
                    },
                  ]}
                />
              </Form.Item>
              <Form.Item name={[field.name, "operator"]} label="比较方式">
                <Select
                  options={[
                    { value: "eq", label: "等于" },
                    { value: "any", label: "任一匹配" },
                    { value: "all", label: "全部匹配" },
                    { value: "range", label: "范围" },
                  ]}
                  onChange={() =>
                    form.setFieldValue(
                      ["conditions", field.name, "value"],
                      null,
                    )
                  }
                />
              </Form.Item>
              {conditions?.[field.name]?.operator === "range" ? (
                <Space>
                  <Form.Item name={[field.name, "minimum"]} label="下限">
                    <InputNumber stringMode />
                  </Form.Item>
                  <Form.Item name={[field.name, "maximum"]} label="上限">
                    <InputNumber stringMode />
                  </Form.Item>
                </Space>
              ) : (
                <Form.Item name={[field.name, "value"]} label="条件值">
                  {["any", "all"].includes(
                    conditions?.[field.name]?.operator ?? "",
                  ) ? (
                    <Select mode="tags" />
                  ) : (
                    <Input />
                  )}
                </Form.Item>
              )}
              <Form.Item name={[field.name, "unit"]} label="单位">
                <Select
                  allowClear
                  options={units.map((value) => ({ value, label: value }))}
                />
              </Form.Item>
              <Button danger onClick={() => remove(field.name)}>
                移除
              </Button>
            </div>
          ))}
          <Button
            onClick={() =>
              add({
                field: "",
                operator: "eq",
                value: null,
                minimum: null,
                maximum: null,
                unit: "",
              })
            }
          >
            添加条件
          </Button>
        </Space>
      )}
    </Form.List>
  );
}
export function KnowledgeFields() {
  const variants = useVariants();
  const form = Form.useFormInstance();
  const kind = Form.useWatch("kind", form);
  return (
    <>
      <Space wrap align="start">
        <Form.Item name="name" label="名称" rules={required}>
          <Input />
        </Form.Item>
        <Form.Item name="kind" label="关系类型">
          <Select
            options={[
              { value: "suitability", label: "系统适用" },
              { value: "accessory", label: "配套关系" },
              { value: "sharing", label: "共用部署" },
            ]}
          />
        </Form.Item>
        <Form.Item name="status" label="确认状态">
          <Select
            options={[
              { value: "draft", label: "草稿" },
              { value: "confirmed", label: "已确认" },
              { value: "disabled", label: "停用" },
            ]}
          />
        </Form.Item>
        <Form.Item name="effect" label="结论">
          <Select
            options={[
              { value: "allow", label: "允许 / 满足条件可用" },
              { value: "deny", label: "禁止 / 明确不兼容" },
            ]}
          />
        </Form.Item>
      </Space>
      <Space wrap align="start">
        <Form.Item
          name={["selector", "variant_ids"]}
          label="适用配置（与类别、系列共同限定）"
        >
          <Select
            mode="multiple"
            style={{ width: 280 }}
            showSearch
            optionFilterProp="label"
            options={variantOptions(variants.data)}
          />
        </Form.Item>
        <Form.Item name={["selector", "category"]} label="类别">
          <Input placeholder="留空不限定" />
        </Form.Item>
        <Form.Item name={["selector", "series"]} label="系列">
          <Select mode="tags" style={{ width: 180 }} />
        </Form.Item>
      </Space>
      <Form.Item
        name={["selector", "exclude_variant_ids"]}
        label="明确排除的配置"
      >
        <Select mode="multiple" options={variantOptions(variants.data)} />
      </Form.Item>
      {kind === "suitability" ? (
        <Space>
          <Form.Item name="system" label="系统类型" rules={required}>
            <Select
              style={{ width: 180 }}
              options={["无纸化", "会议预约"].map((value) => ({
                value,
                label: value,
              }))}
            />
          </Form.Item>
          <Form.Item name="role" label="承担角色" rules={required}>
            <Input placeholder="服务端" />
          </Form.Item>
        </Space>
      ) : null}
      {kind === "sharing" ? (
        <Form.Item
          name="shared_roles"
          label="允许共用的系统 / 角色"
          extra="例如：无纸化/服务端、会议预约/服务端"
        >
          <Select
            mode="tags"
            options={["无纸化/服务端", "会议预约/服务端"].map((value) => ({
              value,
              label: value,
            }))}
          />
        </Form.Item>
      ) : null}
      {kind === "accessory" ? (
        <>
          <Form.Item name="target_variant_ids" label="配件候选配置">
            <Select mode="multiple" options={variantOptions(variants.data)} />
          </Form.Item>
          <Space>
            <Form.Item name="accessory_type" label="配套性质">
              <Select
                options={[
                  { value: "required", label: "必需" },
                  { value: "recommended", label: "推荐" },
                  { value: "optional", label: "可选" },
                ]}
              />
            </Form.Item>
            <Form.Item name="mode" label="数量方式">
              <Select
                options={[
                  { value: "per_unit", label: "每件乘系数" },
                  { value: "per_capacity", label: "按容量向上取整" },
                  { value: "per_group", label: "每个部署项最低数量" },
                ]}
              />
            </Form.Item>
            <Form.Item name="factor" label="数量 / 容量">
              <InputNumber stringMode min="0" />
            </Form.Item>
          </Space>
        </>
      ) : null}
      <ConditionsEditor />
      <AuthorFields />
    </>
  );
}
export function KnowledgeEditor({
  initial,
  onSave,
  onClose,
  busy,
}: {
  initial?: Knowledge;
  onSave: (values: Knowledge) => void;
  onClose: () => void;
  busy: boolean;
}) {
  const [form] = Form.useForm();
  return (
    <Modal
      open
      width={1000}
      title="维护搭配知识"
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={busy}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={initial ?? emptyKnowledge}
        onFinish={(values) =>
          onSave({
            ...values,
            conditions: (values.conditions ?? []).map(
              (c: Knowledge["conditions"][number]) => ({
                ...c,
                unit: c.unit ?? "",
                value: c.value ?? null,
                minimum: c.minimum ?? null,
                maximum: c.maximum ?? null,
              }),
            ),
          })
        }
      >
        <KnowledgeFields />
      </Form>
    </Modal>
  );
}
