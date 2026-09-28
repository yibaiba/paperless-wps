import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Checkbox, ConfigProvider, Form, Input, Modal, Select, Space, Table } from 'antd';
import { api } from '../../../shared/api';
import { ROOT, useVariants, variantOptions } from '../shared';
import type { Knowledge, SystemDefinition } from '../types';
import { normalizeKnowledge } from '../KnowledgeEditor';
import { configurationKeys } from '../queryKeys';
import { ConditionsEditor } from './ConditionsEditor';

export function KnowledgeBatchDialog({ rules, definition, mode, onClose }: {
  rules: Knowledge[]; definition?: SystemDefinition; mode: 'copy' | 'edit'; onClose: () => void;
}) {
  const [form] = Form.useForm(), variants = useVariants();
  const [targets, setTargets] = useState<string[]>([]), [actor, setActor] = useState(''), [evidence, setEvidence] = useState('');
  const [replaceConditions, setReplaceConditions] = useState(false);
  const [preview, setPreview] = useState<{ fingerprint: string; items: unknown[]; operation_id: string }>();
  const generation = useRef(0), client = useQueryClient(), { message } = App.useApp();
  const invalidate = () => { generation.current++; setPreview(undefined); };
  const bulk = useMutation({ mutationFn: async (apply: boolean) => {
    if (apply) {
      if (!preview) throw new Error('请先预览');
      return api(ROOT + '/knowledge/change-apply', { method: 'POST', body: JSON.stringify(preview) });
    }
    if (!actor.trim() || !evidence.trim()) throw new Error('请填写维护人和变更依据');
    if (mode === 'edit' && !targets.length && !replaceConditions) throw new Error('请选择新的配置范围或勾选替换适用条件');
    const conditions = replaceConditions ? (await form.validateFields()).conditions ?? [] : undefined;
    const items = rules.map((k) => ({ ...(mode === 'edit' ? { id: k.id, expected_revision: k.revision } : { expected_revision: 0 }), payload: normalizeKnowledge({ ...k,
      status: 'draft', system_definition_id: definition?.id ?? k.system_definition_id,
      role_id: definition?.roles.find((r) => r.name === k.role)?.id ?? k.role_id,
      name: k.name + (mode === 'copy' ? '（待核对副本）' : ''), actor,
      evidence: `${evidence}；原关系：${k.id} 修订 ${k.revision}。原依据：${k.evidence}`,
      quantity_review: 'unreviewed', reviewed_variant_ids: [], scope_basis: 'listed_configurations',
      ...(conditions ? { conditions } : {}),
      selector: targets.length ? { ...k.selector, variant_ids: targets, category: '', series: [], exclude_variant_ids: [] } : k.selector,
    }) }));
    const version = generation.current;
    const result = await api<{ fingerprint: string }>(ROOT + '/knowledge/change-preview', { method: 'POST', body: JSON.stringify({ items }) });
    if (generation.current !== version) throw new Error('输入已变化，请重新预览');
    setPreview({ fingerprint: result.fingerprint, items, operation_id: crypto.randomUUID() });
  }, onSuccess: (_, applied) => { if (applied) { client.invalidateQueries({ queryKey: configurationKeys.knowledge }); message.success('整批已保存为待核对状态，未确认任何搭配'); onClose(); } }, onError: (e) => message.error(e.message) });
  return <Modal open width={950} title={`${mode === 'copy' ? '复制草稿' : '维护共同条件'} · ${rules.length} 条`} closable={!bulk.isPending} mask={{ closable: false }} onCancel={onClose}
    footer={<Space><Button loading={bulk.isPending} onClick={() => bulk.mutate(false)}>预览整批</Button><Button type="primary" disabled={!preview || bulk.isPending} onClick={() => bulk.mutate(true)}>确认整批保存</Button></Space>}>
    <ConfigProvider componentDisabled={bulk.isPending}><Space orientation="vertical" style={{ width: '100%' }}>
      <Alert type="info" title={mode === 'edit' ? '修改已有关系会生成新修订，并将本批关系与数量依据改为待核对。历史项目及知识包仍保留原修订。' : '创建独立草稿，原关系保持不变。确认状态和已核对配置范围不继承。'} />
      <Select mode="multiple" placeholder="重新指定适用配置；留空保留原范围" value={targets} onChange={(v) => { setTargets(v); invalidate(); }} options={variantOptions(variants.data)} style={{ width: '100%' }} />
      <Checkbox checked={replaceConditions} onChange={(e) => { setReplaceConditions(e.target.checked); invalidate(); }}>替换适用条件（条件列表留空表示清空）</Checkbox>
      {replaceConditions ? <Form form={form} layout="vertical" initialValues={{ conditions: [] }} onValuesChange={invalidate}><ConditionsEditor /></Form> : null}
      <Input placeholder="维护人" value={actor} onChange={(e) => { setActor(e.target.value); invalidate(); }} />
      <Input.TextArea placeholder="变更目的和待核对依据" value={evidence} onChange={(e) => { setEvidence(e.target.value); invalidate(); }} />
      {preview ? <><Alert type="info" title={`已预览 ${preview.items.length} 条：状态均为草稿；数量和配置范围均需重新确认。`} />
        <Table rowKey="id" size="small" dataSource={rules} pagination={false} columns={[
          { title: '关系', dataIndex: 'name' }, { title: '原修订', dataIndex: 'revision' }, { title: '变更', render: () => `${targets.length ? `${targets.length} 个配置` : '保留原范围'}；${replaceConditions ? '替换条件' : '保留原条件'}；待核对` },
        ]} /></> : null}
    </Space></ConfigProvider>
  </Modal>;
}
