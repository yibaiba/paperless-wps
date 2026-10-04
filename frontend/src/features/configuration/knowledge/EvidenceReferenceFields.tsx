import { useState } from "react";
import { WorkbookEvidence } from "../materials/WorkbookEvidence";
import { Button, Drawer, Form, Input, Select, Space, Typography } from "antd";
import { useVariants } from "../shared";

export function EvidenceReferenceFields({ name = "evidence_refs", path }: { name?: string | (string | number)[]; path?: (string | number)[] }) {
  const [materialOpen, setMaterialOpen] = useState(false);
  const fullPath = path ?? (Array.isArray(name) ? name : [name]);
  const variants = useVariants();
  const form = Form.useFormInstance();
  const sources = [...new Map(variants.data?.flatMap((v) => v.source_details ?? []).map((s) => [s.id, s])).values()];
  return <Form.List name={name}>{(fields, { add, remove }) => <Space orientation="vertical" style={{ width: "100%" }}>
    {fields.map((field) => <div key={field.key}>
      {["material_id", "material_revision", "segment_id"].map(key => <Form.Item key={key} name={[field.name, key]} hidden><Input /></Form.Item>)}
      {form.getFieldValue([...fullPath, field.name, "material_id"]) ? <Typography.Paragraph>工作簿资料 · 修订 {form.getFieldValue([...fullPath, field.name, "material_revision"])}</Typography.Paragraph> : <Form.Item name={[field.name, "source_id"]} label="原始来源" rules={[{ required: true }]}><Select showSearch optionFilterProp="label"
        options={sources.map((s) => ({ value: s.id, label: `${s.sheet} · 第 ${s.row} 行 · ${s.specification?.slice(0, 35) ?? ""}` }))}
        onChange={(id) => { const source = sources.find((s) => s.id === id); form.setFieldValue([...fullPath, field.name, "locator"], source ? `${source.sheet} · 第 ${source.row} 行` : ""); }} /></Form.Item>}
      <Form.Item name={[field.name, "locator"]} label="原文位置" rules={[{ required: true }]}><Input /></Form.Item>
      <Form.Item name={[field.name, "quote"]} label="原文摘录" rules={[{ required: true }]}><Input.TextArea /></Form.Item>
      <Button onClick={() => remove(field.name)}>移除引用</Button>
    </div>)}
    <Drawer title="引用工作簿说明" width={780} open={materialOpen} onClose={() => setMaterialOpen(false)}><WorkbookEvidence onReference={ref => { add(ref); setMaterialOpen(false); }} /></Drawer>
    <Button onClick={() => setMaterialOpen(true)}>引用工作簿说明</Button>
    <Button onClick={() => add({ source_id: "", locator: "", quote: "" })}>引用原始产品资料</Button>
  </Space>}</Form.List>;
}
