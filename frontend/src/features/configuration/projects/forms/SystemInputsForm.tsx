import { useState } from "react";
import { Form, InputNumber, Modal, Typography } from "antd";
import type { Attribute, Configuration, System } from "../../types";
import { useDefinitions } from "../../knowledge/useDefinitions";
import { AttributeEditor, cleanAttributes } from "../../shared";
import { combineInputs, initialInputs, systemMetrics } from "./inspectionInputs";

export function SystemInputsForm({ system, configuration, onApply, onClose }: {
  system: System; configuration: Configuration;
  onApply: (inputs: Attribute[]) => void; onClose: () => void;
}) {
  const definitions = useDefinitions(configuration.definition_snapshot_id);
  const metrics = systemMetrics(system, configuration, definitions.data);
  const [form] = Form.useForm();
  const [error, setError] = useState<string>();
  const ambiguous = metrics.some((m) => metrics.some((other) => other.input_key === m.input_key && other.input_unit !== m.input_unit));
  const existing = system.inputs ?? [];
  return <Modal open width={780} title={`${system.name} · 项目需求`} onCancel={onClose}
    okButtonProps={{ disabled: definitions.isPending || !!definitions.error || ambiguous }} onOk={() => form.submit()}>
    <Typography.Paragraph type="secondary">同一系统填写一次，已建立的相关角色和配套计算复用。留空会提示缺少输入；与角色手工参数不同会明确提示冲突。</Typography.Paragraph>
    {ambiguous ? <Typography.Paragraph type="danger">同一输入存在不同单位，请维护者先统一用途检查定义。</Typography.Paragraph> : null}
    {definitions.error || error ? <Typography.Paragraph type="danger">{definitions.error?.message ?? error}</Typography.Paragraph> : null}
    {definitions.data ? <Form form={form} layout="vertical" initialValues={initialInputs(existing, metrics)} onFinish={(values) => {
      try {
        const inputs = combineInputs(metrics, values.values ?? {}, cleanAttributes(values.extra));
        setError(undefined); onApply(inputs); onClose();
      } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    }}>
      {metrics.map((m) => {
        const original = existing.find((a) => a.key === m.input_key);
        const changedUnit = original && original.unit !== m.input_unit;
        return <Form.Item key={`${m.input_key}:${m.input_unit}`} name={["values", m.input_key]} label={`${m.input_label}（${m.input_unit}）`}
          extra={changedUnit ? `原值：${original.value ?? "未知"} ${original.unit || "无单位"}。单位已变化，请核对并明确填写新值，不会自动换算。` : undefined}
          rules={changedUnit ? [{ required: true, message: "请明确填写新单位下的数值，或取消保留原值" }] : []}>
          <InputNumber stringMode min="0" style={{ width: "100%" }} />
        </Form.Item>;
      })}
      {!metrics.length ? <Typography.Paragraph>当前角色还未关联用途检查，可先填写项目输入，随后由维护者关联检查定义。</Typography.Paragraph> : null}
      <Typography.Paragraph type="secondary">其他项目输入（保留自定义字段）</Typography.Paragraph>
      <AttributeEditor name="extra" />
    </Form> : null}
  </Modal>;
}
