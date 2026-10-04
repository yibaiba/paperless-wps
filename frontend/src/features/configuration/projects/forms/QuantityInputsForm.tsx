import { useState } from 'react';
import { Alert, Form, InputNumber, Modal, Typography } from 'antd';
import type { Configuration, QuantityInputIssue } from '../../types';
import { applyQuantityInputs, quantityScopeLabel, scopedInputs } from './quantityInputEdits';

export function QuantityInputsForm({ configuration, inputs, onApply, onClose }: {
  configuration: Configuration; inputs: QuantityInputIssue[];
  onApply: (value: Configuration) => void; onClose: () => void;
}) {
  const [form] = Form.useForm<{ values: (string | null)[] }>();
  const [error, setError] = useState<string>();
  const current = readInputs(configuration, inputs);
  if (current.error) return <Modal open title="数量需求已变化" footer={null} onCancel={onClose}><Alert type="error" showIcon title={current.error} /></Modal>;
  const existing = current.existing;
  const changedUnits = inputs.map((input, index) => existing[index] && existing[index]?.unit !== input.unit);
  return <Modal open title="补充配套数量需求" onCancel={onClose} onOk={() => form.submit()}>
    <Typography.Paragraph>只修改下列项目需求。留空表示未知，0 表示明确为零；不会自动加入采购产品。</Typography.Paragraph>
    {error ? <Alert type="error" showIcon title={error} /> : null}
    <Form form={form} layout="vertical" initialValues={{ values: existing.map((a, index) => changedUnits[index] ? null : a?.value ?? null) }} onFinish={values => {
      try { onApply(applyQuantityInputs(configuration, inputs, values.values)); onClose(); }
      catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    }}>
      {inputs.map((input, index) => <Form.Item key={`${input.scope}:${input.scope_id}:${input.key}`} name={['values', index]}
        label={`${quantityScopeLabel(configuration, input)} · ${input.label}${input.unit ? `（${input.unit}）` : ''}`}
        extra={changedUnits[index] ? `原值 ${existing[index]?.value ?? '未知'} ${existing[index]?.unit}；请核对新单位，不会自动换算。` : input.message}
        rules={changedUnits[index] ? [{ required: true, message: '请填写核对后的数值，或取消保留原值' }] : []}>
        <InputNumber stringMode min="0" style={{ width: '100%' }} />
      </Form.Item>)}
    </Form>
  </Modal>;
}

function readInputs(configuration: Configuration, inputs: QuantityInputIssue[]) {
  try { return { existing: inputs.map(input => scopedInputs(configuration, input).find(a => a.key === input.key)), error: undefined }; }
  catch (failure) { return { existing: [], error: failure instanceof Error ? failure.message : String(failure) }; }
}
