import { Button, Form, Input, Select, Space } from "antd";
import { useVariants } from "../shared";

export function EvidenceReferenceFields() {
  const variants = useVariants();
  const form = Form.useFormInstance();
  const sources = [...new Map(variants.data?.flatMap((v) => v.source_details ?? []).map((s) => [s.id, s])).values()];
  return <Form.List name="evidence_refs">{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: "100%" }}>
    {fields.map((field) => <div key={field.key}>
      <Form.Item name={[field.name, "source_id"]} label="原始来源" rules={[{ required: true }]}><Select showSearch optionFilterProp="label"
        options={sources.map((s) => ({ value: s.id, label: `${s.sheet} · 第 ${s.row} 行 · ${s.specification?.slice(0, 35) ?? ""}` }))}
        onChange={(id) => { const source = sources.find((s) => s.id === id); form.setFieldValue(["evidence_refs", field.name, "locator"], source ? `${source.sheet} · 第 ${source.row} 行` : ""); }} /></Form.Item>
      <Form.Item name={[field.name, "locator"]} label="原文位置" rules={[{ required: true }]}><Input /></Form.Item>
      <Form.Item name={[field.name, "quote"]} label="原文摘录" rules={[{ required: true }]}><Input.TextArea /></Form.Item>
      <Button onClick={() => remove(field.name)}>移除引用</Button>
    </div>)}
    <Button onClick={() => add({ source_id: "", locator: "", quote: "" })}>引用原始产品资料</Button>
  </Space>}</Form.List>;
}
