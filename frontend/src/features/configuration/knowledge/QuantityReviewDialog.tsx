import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Form, Input, Modal, Select, Typography } from 'antd';
import type { Knowledge } from '../types';
import { api } from '../../../shared/api';
import { ROOT, required, useVariants, variantOptions } from '../shared';
import { normalizeKnowledge } from '../KnowledgeEditor';
import { configurationKeys } from '../queryKeys';
import { AccessoryCalculationFields } from './KnowledgeRuleStep';
import { SourceEvidencePanel } from './SourceEvidencePanel';
import { EvidenceReferenceFields } from './EvidenceReferenceFields';
import { matchingConfigurations } from './quickEdit';
import { quantityValues } from './reconciliation';

export function QuantityReviewDialog({ rule, onClose }: { rule: Knowledge; onClose: () => void }) {
  const [form] = Form.useForm<Knowledge>(), variants = useVariants(), client = useQueryClient();
  const source = Form.useWatch('quantity_source', form);
  const targets = Form.useWatch('target_variant_ids', form) ?? rule.target_variant_ids;
  const selected = new Set([...matchingConfigurations(rule, variants.data ?? []).map(v => v.id), ...targets]);
  const save = useMutation({ mutationFn: (values: Knowledge) => api(ROOT + '/knowledge/' + rule.id, {
    method: 'PUT', body: JSON.stringify({ expected_revision: rule.revision, payload: normalizeKnowledge(quantityValues(rule, values)) }),
  }), onSuccess: async () => { await client.invalidateQueries({ queryKey: configurationKeys.knowledge }); onClose(); } });
  return <Modal open width={1160} title={`核对数量依据 · ${rule.name}`} okText="保存数量修订" confirmLoading={save.isPending}
    closable={!save.isPending} mask={{ closable: false }} onCancel={onClose} onOk={() => form.submit()}>
    <Alert type="info" title="关系状态保持不变，数量单独确认" description="对照原文核对候选和数量口径；不能确定时保存待确认。保存后需明确将新修订纳入知识包，历史项目保持原版本。" />
    {save.error || variants.error ? <Alert type="error" title={save.error?.message ?? variants.error?.message} /> : null}
    <Form form={form} layout="vertical" initialValues={rule} disabled={save.isPending} onFinish={values => save.mutate(values)}>
      <div className="knowledge-workbench"><div>
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>原关系依据：{rule.evidence}</Typography.Paragraph>
        <Form.Item name="target_variant_ids" label="同一需求的替代候选（不是全部采购）"><Select mode="multiple" showSearch optionFilterProp="label" options={variantOptions(variants.data)} /></Form.Item>
        <AccessoryCalculationFields quantitySource={source} includeNeedKey={false} />
        <Form.Item name="quantity_review" label="数量核对结论"><Select options={[{ value: 'unreviewed', label: '仍待确认' }, { value: 'confirmed', label: '已逐项核对数量依据' }]} /></Form.Item>
        <Form.Item name="quantity_evidence" label="数量依据与适用口径"><Input.TextArea placeholder="原文如何支持计算范围、数量输入、系数；不能确定时说明缺少什么" /></Form.Item>
        <Form.Item name="actor" label="本次维护人" rules={required}><Input /></Form.Item>
        <EvidenceReferenceFields />
      </div><aside><Typography.Title level={5}>产品原文</Typography.Title><SourceEvidencePanel variants={(variants.data ?? []).filter(v => selected.has(v.id))} /></aside></div>
    </Form>
  </Modal>;
}
