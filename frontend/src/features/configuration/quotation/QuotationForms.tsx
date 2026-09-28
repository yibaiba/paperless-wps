import { Form, Input, InputNumber, Modal, Select } from "antd";
import type { Quotation, QuotedPrice, QuoteTemplate } from "./types";
import type { Deployment } from "../types";

export function QuotationForm({ value, template, projectName, onApply, onClose }: {
  value?: Quotation | null; template: QuoteTemplate; projectName: string;
  onApply: (value: Quotation) => void; onClose: () => void;
}) {
  const [form] = Form.useForm();
  const initial: Quotation = value ?? {
    template_id: template.id, currency: "CNY", customer: "", project_name: projectName,
    sales_contact: "", designer_contact: "", design_date: null, room_description: "",
    price_column: "", tax_terms: template.tax_terms, prices: [], sections: {},
  };
  return <Modal open title="报价资料与采用价格" onCancel={onClose} onOk={() => form.submit()}>
    <Form form={form} layout="vertical" initialValues={initial} onFinish={(fields) => {
      onApply({ ...initial, ...fields, design_date: fields.design_date || null }); onClose();
    }}>
      <Form.Item label="采用产品库价格列" name="price_column"><Select allowClear options={template.price_columns.map((p) => ({ value: p, label: p }))} onClear={() => form.setFieldValue("price_column", "")} /></Form.Item>
      <Form.Item label="客户名称" name="customer"><Input /></Form.Item>
      <Form.Item label="项目名称" name="project_name"><Input /></Form.Item>
      <Form.Item label="销售经理 / 联系电话" name="sales_contact"><Input /></Form.Item>
      <Form.Item label="设计人员 / 联系电话" name="designer_contact"><Input /></Form.Item>
      <Form.Item label="设计日期" name="design_date"><Input type="date" /></Form.Item>
      <Form.Item label="厅堂名称及尺寸面积" name="room_description"><Input.TextArea rows={2} /></Form.Item>
      <p>{template.tax_terms}</p>
    </Form>
  </Modal>;
}

export function PriceForm({ device, quotation, onApply, onClose }: {
  device: Deployment; quotation: Quotation;
  onApply: (value: Quotation) => void; onClose: () => void;
}) {
  const [form] = Form.useForm();
  const previous = quotation.prices.find((p) => p.device_id === device.id);
  const mode = Form.useWatch("mode", form) ?? (previous?.mode === "import" ? "manual" : previous?.mode) ?? "source";
  return <Modal open title={`报价单价 · ${device.name}`} onCancel={onClose} onOk={() => form.submit()}>
    <Form form={form} layout="vertical" initialValues={{ mode: (previous?.mode === "import" ? "manual" : previous?.mode) ?? "source", unit_price: previous?.unit_price, evidence: previous?.evidence ?? "", section: quotation.sections[device.id] ?? "" }} onFinish={(fields) => {
      const price: QuotedPrice = { device_id: device.id, variant_id: device.variant_id,
        source_id: device.source_id, mode: fields.mode, price_column: quotation.price_column,
        unit_price: fields.mode === "manual" ? String(fields.unit_price) : null,
        evidence: fields.evidence || "重新采用本次报价价格列" };
      onApply({ ...quotation, prices: [...quotation.prices.filter((p) => p.device_id !== device.id), price], sections: { ...quotation.sections, [device.id]: fields.section ?? "" } });
      onClose();
    }}>
      <Form.Item label="采用方式" name="mode"><Select options={[{ value: "source", label: "重新采用报价指定价格列" }, { value: "manual", label: "人工指定单价" }]} /></Form.Item>
      {mode === "manual" ? <>
        <Form.Item label="单价（人民币，含税含运）" name="unit_price" rules={[{ required: true }]}><InputNumber stringMode min="0" style={{ width: "100%" }} /></Form.Item>
        <Form.Item label="调整依据" name="evidence" rules={[{ required: true, whitespace: true }]}><Input.TextArea /></Form.Item>
      </> : null}
      <Form.Item label="报价展示分区（留空按服务系统分组）" name="section"><Input /></Form.Item>
    </Form>
  </Modal>;
}
