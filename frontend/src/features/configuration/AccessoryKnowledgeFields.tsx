import { Form, Input, Select, Space } from "antd";
import type { Knowledge } from "./types";
import { useVariants, variantOptions } from "./shared";
import { KnowledgeRuleStep } from "./knowledge/KnowledgeRuleStep";

export function AccessoryKnowledgeFields() {
  const variants = useVariants(), form = Form.useFormInstance();
  const quantitySource = Form.useWatch("quantity_source", form) as Knowledge["quantity_source"] | undefined;
  return <>
    <Space wrap align="start">
      <Form.Item name="need_name" label="需要什么配套"><Input placeholder="例如：服务器、会议主机" /></Form.Item>
      <Form.Item name="accessory_type" label="配套性质"><Select options={[
        { value: "required", label: "必需" }, { value: "recommended", label: "推荐" }, { value: "optional", label: "可选" },
      ]} /></Form.Item>
    </Space>
    <Form.Item name="target_variant_ids" label="可替代的候选配置" extra="尚未明确型号时可留空，系统会显示待确认。">
      <Select mode="multiple" showSearch optionFilterProp="label" options={variantOptions(variants.data)} />
    </Form.Item>
    <KnowledgeRuleStep kind="accessory" quantitySource={quantitySource} summary="先记录需要什么，再核对候选和数量依据" />
  </>;
}
