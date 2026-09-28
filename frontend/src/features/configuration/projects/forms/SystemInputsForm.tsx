import { Form, InputNumber, Modal, Typography } from "antd";
import type { Attribute, Configuration, Definitions, System } from "../../types";
import { useDefinitions } from "../../knowledge/useDefinitions";
import { AttributeEditor, cleanAttributes } from "../../shared";
import type { InspectionMetric } from "../../knowledge/inspectionTypes";

function systemMetrics(system: System, definitions?: Definitions) {
  const packageValue = definitions?.packages.find((p) => p.id === system.knowledge_package_id);
  const definition = packageValue?.definition ?? definitions?.definitions.find((d) => d.id === system.definition_id);
  const metrics = new Map<string, InspectionMetric>();
  for (const profile of definition?.inspection_profiles ?? []) for (const metric of profile.metrics) {
    metrics.set(`${metric.input_key}:${metric.input_unit}`, metric);
  }
  return [...metrics.values()];
}
export function SystemInputsForm({ system, configuration, onApply, onClose }: {
  system: System; configuration: Configuration; onApply: (inputs: Attribute[]) => void; onClose: () => void;
}) {
  const definitions = useDefinitions(configuration.definition_snapshot_id);
  const metrics = systemMetrics(system, definitions.data);
  const [form] = Form.useForm();
  const ambiguous = metrics.some((m) => metrics.some((other) => other.input_key === m.input_key && other.input_unit !== m.input_unit));
  const existing = system.inputs ?? [];
  return <Modal open width={780} title={`${system.name} · 项目需求`} onCancel={onClose} okButtonProps={{ disabled: definitions.isPending || !!definitions.error || ambiguous }} onOk={() => form.submit()}>
    <Typography.Paragraph type="secondary">同一系统填写一次，相关角色和配套计算复用。留空会提示缺少输入；与角色手工参数不同会明确提示冲突。</Typography.Paragraph>
    {ambiguous ? <Typography.Paragraph type="danger">同一输入存在不同单位，请维护者先统一用途检查定义。</Typography.Paragraph> : null}
    {definitions.error ? <Typography.Text type="danger">{definitions.error.message}</Typography.Text> : null}
    {definitions.data ? <Form form={form} layout="vertical" initialValues={{ values: Object.fromEntries(existing.map((a) => [a.key, a.value])), extra: existing.filter((a) => !metrics.some((m) => m.input_key === a.key)) }} onFinish={(values) => {
      const inputs: Attribute[] = metrics.filter((m, i) => metrics.findIndex((v) => v.input_key === m.input_key) === i).map((m) => ({ key: m.input_key, kind: "quantity", value: values.values?.[m.input_key] ?? null, unit: m.input_unit }));
      onApply([...inputs, ...cleanAttributes(values.extra).filter((a) => !metrics.some((m) => m.input_key === a.key))]); onClose();
    }}>
      {metrics.map((m) => <Form.Item key={`${m.input_key}:${m.input_unit}`} name={["values", m.input_key]} label={`${m.input_label}（${m.input_unit}）`}><InputNumber stringMode min="0" style={{ width: "100%" }} /></Form.Item>)}
      {!metrics.length ? <Typography.Paragraph>该系统还未关联用途检查，可先填写项目输入，随后由维护者关联检查定义。</Typography.Paragraph> : null}
      <Typography.Paragraph type="secondary">其他项目输入（保留自定义字段）</Typography.Paragraph>
      <AttributeEditor name="extra" />
    </Form> : null}
  </Modal>;
}
