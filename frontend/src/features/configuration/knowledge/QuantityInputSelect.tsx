import { Alert, AutoComplete, Form } from 'antd';
import { useAttributeDefinitions } from '../shared';
import { useDefinitions } from './useDefinitions';

export function QuantityInputSelect({ value, onChange, id }: { value?: string; onChange?: (value: string) => void; id?: string }) {
  const attributes = useAttributeDefinitions(), definitions = useDefinitions(), form = Form.useFormInstance();
  const fields = [...(attributes.data ?? []).filter(d => ['number', 'quantity'].includes(d.kind)).map(d => ({ key: d.key, label: d.label, units: d.units })),
    ...(definitions.data?.inspection_profiles ?? []).flatMap(p => p.metrics.map(m => ({ key: m.input_key, label: m.input_label, units: [m.input_unit] })))];
  const options = [...new Map(fields.map(f => [f.key, { value: f.key, label: `${f.label} · ${f.key}` }])).values()];
  return <>{attributes.error || definitions.error ? <Alert type="error" title={attributes.error?.message ?? definitions.error?.message} /> : null}<AutoComplete id={id} value={value} onChange={onChange} style={{ width: 240 }} options={options} placeholder="选择需求参数或保留自定义键" onSelect={key => {
    const units = [...new Set(fields.filter(f => f.key === key).flatMap(f => f.units))];
    if (units.length === 1) form.setFieldValue('quantity_unit', units[0]);
  }} /></>;
}
