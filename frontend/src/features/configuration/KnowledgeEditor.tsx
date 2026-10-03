import { CombinationFields } from "./knowledge/CombinationFields";
import { ConditionsEditor } from "./knowledge/ConditionsEditor";
export { ConditionsEditor } from "./knowledge/ConditionsEditor";
import {
  Form,
  Input,
  Modal,
  Select,
  Space,
} from "antd";
import type { Knowledge } from "./types";
import { AccessoryKnowledgeFields } from "./AccessoryKnowledgeFields";
import { EvidenceReferenceFields } from "./knowledge/EvidenceReferenceFields";
import { KnowledgeIdentityFields } from "./knowledge/KnowledgeIdentityFields";
import { SharedRoleSelect } from "./knowledge/SharedRoleSelect";
import { SystemTypeInput } from "./SystemTypeInput";
import {
  AuthorFields,
  required,
  useVariants,
  variantOptions,
} from "./shared";

export const emptyKnowledge = {
  schema_version: 2,
  system_definition_id: "",
  role_id: "",
  activation_conditions: [],
  alternative_group: "",
  quantity_review: "unreviewed",
  quantity_evidence: "",
  resource_policy: "unknown",
  evidence_refs: [],
  shared_role_refs: [],
  scope_basis: "listed_configurations",
  reviewed_variant_ids: [],
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
  need_key: "",
  need_name: "",
  target_variant_ids: [],
  accessory_type: "required",
  calculation_scope: null,
  quantity_source: "device_quantity",
  quantity_key: "",
  quantity_unit: "",
  mode: null,
  factor: null,
  output_kind: "accessory",
  allocation_mode: "consumable",
  shared_roles: [],
};
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
              { value: "combination", label: "互斥 / 必选组合" },
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
        <Space wrap align="start">
          <Form.Item
            name="system"
            label="系统 / 方案版本"
            rules={required}
            style={{ width: 320 }}
          >
            <SystemTypeInput />
          </Form.Item>
          <Form.Item name="role" label="承担角色" rules={required}>
            <Input placeholder="服务端" />
          </Form.Item>
        </Space>
      ) : null}
      {kind === "sharing" ? (
        <>
        <Form.Item name="shared_role_refs" label="共用的系统与角色定义" extra="使用稳定标识关联，系统或角色改名后关系仍保留；填写后按此关联检查。">
          <SharedRoleSelect />
        </Form.Item>
        <Form.Item
          name="shared_roles"
          label="历史文本关联（未关联定义时使用）"
          extra="填写具体系统版本和角色；各自可用不代表能够共用部署。"
        >
          <Select
            mode="tags"
            options={[
              ...new Set(variants.data?.flatMap((v) => v.systems) ?? []),
            ].map((system) => ({ value: system + "/服务端" }))}
          />
        </Form.Item>
        </>
      ) : null}
      {kind === "combination" ? <CombinationFields variants={variants.data} /> : null}
      {kind === "accessory" ? (
        <AccessoryKnowledgeFields />
      ) : null}
      <KnowledgeIdentityFields />
      {kind !== "accessory" ? <ConditionsEditor /> : null}
      <EvidenceReferenceFields />
      <AuthorFields />
    </>
  );
}
export function normalizeKnowledge(values: Knowledge & { updated_at?: string }): Knowledge {
  const payload = Object.fromEntries(Object.entries(values).filter(([key]) =>
    !["id", "revision", "updated_at", "completion", "missing_fields"].includes(key))) as unknown as Knowledge;
  return {
    ...payload,
    schema_version: 2,
    combination: values.kind === "combination" ? values.combination : null,
    activation_conditions: (values.activation_conditions ?? []).map((c) => ({
      ...c, unit: c.unit ?? "", value: c.value ?? null,
      minimum: c.minimum ?? null, maximum: c.maximum ?? null,
    })),
    completion: undefined,
    missing_fields: undefined,
    conditions: (values.conditions ?? []).map((condition) => ({
      ...condition,
      unit: condition.unit ?? "",
      value: condition.value ?? null,
      minimum: condition.minimum ?? null,
      maximum: condition.maximum ?? null,
    })),
  };
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
        onFinish={(values) => onSave(normalizeKnowledge({ ...initial, ...values }))}
      >
        <KnowledgeFields />
      </Form>
    </Modal>
  );
}
