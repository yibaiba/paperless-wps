import { EvidenceReferenceFields } from "../knowledge/EvidenceReferenceFields";
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space } from "antd";
import { required, useKnowledge, useVariants, variantOptions } from "../shared";

export function IncludedItemsEditor({ hostId }: { hostId?: string }) {
  const variants = useVariants();
  const knowledge = useKnowledge();
  const needs = [...new Map(knowledge.data?.filter((k) => k.kind === "accessory" && k.need_key)
    .map((k) => [k.need_key, { value: k.need_key, label: `${k.need_name || k.name} · ${k.need_key}` }])).values()];
  return <Card size="small" title="此配置已含的软件／配件">
    <Alert type="info" showIcon title="仅记录有依据的包含内容；项目明确关联配套需求后才抵扣。"
      description="数量按每单位宿主配置填写。内置功能未对应独立配置、授权范围或数量尚不清楚时保留草稿。" />
    {variants.error || knowledge.error ? <Alert type="error" title="候选或需求加载失败" description={(variants.error || knowledge.error)?.message} /> : null}
    <Form.List name="included_items">{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: "100%" }}>
      {fields.map((field) => <Card size="small" key={field.key} extra={<Button danger onClick={() => remove(field.name)}>移除此包含项</Button>}>
        <Form.Item name={[field.name, "id"]} hidden><Input /></Form.Item>
        <Space wrap align="start">
          <Form.Item name={[field.name, "name"]} label="包含内容名称" rules={required}><Input /></Form.Item>
          <Form.Item name={[field.name, "kind"]} label="计量类型" rules={required}>
            <Select style={{ width: 120 }} options={[
              { value: "software", label: "软件" }, { value: "license", label: "授权" },
              { value: "accessory", label: "配件" }, { value: "hardware", label: "硬件" },
            ]} />
          </Form.Item>
          <Form.Item name={[field.name, "quantity"]} label="每单位包含数量"><InputNumber stringMode /></Form.Item>
          <Form.Item name={[field.name, "status"]} label="依据状态" rules={required}>
            <Select style={{ width: 130 }} options={[
              { value: "draft", label: "草稿／待确认" }, { value: "confirmed", label: "已确认" }, { value: "disabled", label: "停用" },
            ]} />
          </Form.Item>
        </Space>
        <Form.Item name={[field.name, "variant_id"]} label="包含的具体配置（未知可留空）">
          <Select allowClear showSearch optionFilterProp="label" options={variantOptions(variants.data?.filter((v) => v.id !== hostId))} />
        </Form.Item>
        <Form.Item name={[field.name, "need_keys"]} label="可满足的配套需求">
          <Select mode="multiple" showSearch optionFilterProp="label" options={needs} placeholder="选择明确对应的配套需求" />
        </Form.Item>
        <Form.Item name={[field.name, "evidence"]} label="包含及数量依据"><Input.TextArea placeholder="资料位置、原文、适用版本和数量口径" /></Form.Item>
        <EvidenceReferenceFields name={[field.name, "evidence_refs"]} path={["included_items", field.name, "evidence_refs"]} />
      </Card>)}
      <Button onClick={() => add({ id: crypto.randomUUID(), name: "", kind: "accessory", status: "draft", quantity: null, variant_id: null, need_keys: [], evidence: "" })}>添加已含内容</Button>
    </Space>}</Form.List>
  </Card>;
}
