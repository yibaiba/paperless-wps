import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, ConfigProvider, Drawer, Input, Select, Space, Table, Typography } from 'antd';
import type { Knowledge, KnowledgePackage } from '../types';
import { api } from '../../../shared/api';
import { ROOT, Status } from '../shared';
import { normalizeKnowledge } from '../KnowledgeEditor';
import { configurationKeys } from '../queryKeys';
import { KnowledgePackageEditor } from './KnowledgePackageEditor';
import { definitionsKey, packagesKey } from './useDefinitions';
import { QuantityReviewDialog } from './QuantityReviewDialog';
import { mappingValues, quantityDescription, reconciliationRows, roleSuggestion } from './reconciliation';

type MappingItem = { id: string; expected_revision: number; payload: Knowledge };
type Preview = { fingerprint: string; operation_id: string; items: MappingItem[] };

export function KnowledgeReconciliation({ bundle, knowledge, packages, onClose, onAdvanced }: {
  bundle: KnowledgePackage; knowledge: Knowledge[]; packages: KnowledgePackage[]; onClose: () => void; onAdvanced: (rule: Knowledge) => void;
}) {
  const [roles, setRoles] = useState<Record<string, string>>({}), [selected, setSelected] = useState<string[]>([]);
  const [actor, setActor] = useState(''), [evidence, setEvidence] = useState('');
  const [preview, setPreview] = useState<Preview>(), [quantity, setQuantity] = useState<Knowledge>();
  const [editPackage, setEditPackage] = useState(false), [notice, setNotice] = useState('');
  const generation = useRef(0), client = useQueryClient();
  const rows = reconciliationRows(bundle, knowledge), definition = bundle.definition;
  const invalidate = () => { generation.current++; setPreview(undefined); };
  const bulk = useMutation({ mutationFn: async (apply: boolean) => {
    if (apply) {
      if (!preview) throw new Error('请先预览本次归属修改');
      await api(ROOT + '/knowledge/change-apply', { method: 'POST', body: JSON.stringify(preview) });
      await client.invalidateQueries({ queryKey: configurationKeys.knowledge });
      setSelected([]); setRoles({}); invalidate();
      setNotice('归属新修订已保存。原知识包仍使用旧修订，请点击“整理知识包变更”明确采用。');
      return;
    }
    if (!selected.length) throw new Error('请勾选需要确认归属的关系');
    const items = selected.map(id => {
      const rule = knowledge.find(item => item.id === id);
      if (!rule) throw new Error('原关系不可用，请刷新核对');
      const payload = normalizeKnowledge(mappingValues({ rule, definition, roleId: roles[id], actor, evidence }));
      return { id, expected_revision: rule.revision, payload: { ...payload, schema_version: rule.schema_version ?? 1 } };
    });
    const version = generation.current;
    const result = await api<{ fingerprint: string }>(ROOT + '/knowledge/change-preview', { method: 'POST', body: JSON.stringify({ items }) });
    if (generation.current !== version) throw new Error('选择已变化，请重新预览');
    setPreview({ fingerprint: result.fingerprint, items, operation_id: crypto.randomUUID() });
  } });
  const savePackage = useMutation({ mutationFn: (payload: unknown) => api(`${ROOT}/knowledge-packages/${bundle.id}`, {
    method: 'PUT', body: JSON.stringify({ expected_revision: bundle.revision, payload }),
  }), onSuccess: async () => {
    await Promise.all([client.invalidateQueries({ queryKey: packagesKey }), client.invalidateQueries({ queryKey: definitionsKey })]);
    setEditPackage(false); setNotice('知识包已保存所选修订，原项目快照未改变。');
  } });
  return <><Drawer open size={1180} title={`归属与数量核对 · ${bundle.name}`} onClose={onClose} closable={!bulk.isPending && !savePackage.isPending}
    extra={<Button disabled={bulk.isPending} onClick={() => setEditPackage(true)}>整理知识包变更</Button>}>
    <ConfigProvider componentDisabled={bulk.isPending || savePackage.isPending}><Space orientation="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="info" title={`按本包角色定义 v${definition.revision} 核对，逐条选择后整批预览`} description="同名提示仅帮助定位，不自动选择。确认归属保留关系与数量的原确认状态；其他包与历史项目保留固定修订。通用配套不必强行指定角色，共享关系使用高级编辑。" />
      {notice ? <Alert type="success" title={notice} /> : null}
      {bulk.error || savePackage.error ? <Alert type="error" title={bulk.error?.message ?? savePackage.error?.message} /> : null}
      <Table rowKey={row => row.fixed.id} dataSource={rows} pagination={false} scroll={{ x: 1060 }}
        rowSelection={{ selectedRowKeys: selected, onChange: keys => { setSelected(keys as string[]); invalidate(); }, getCheckboxProps: row => ({ disabled: !row.current || row.current.kind === 'sharing' || !roles[row.fixed.id] }) }}
        columns={[
          { title: '关系与修订', width: 230, render: (_, row) => <><strong>{row.fixed.name}</strong><div>包内 v{row.fixed.revision} · 当前 {row.current ? `v${row.current.revision}` : '不可用'}</div><Status value={row.current?.status ?? 'unknown'} />{row.current && row.current.revision !== row.fixed.revision ? <div>新修订尚未纳入本包</div> : null}</> },
          { title: '原归属 / 本次映射', width: 260, render: (_, { current: rule }) => rule ? <>
            <Typography.Paragraph>{rule.system || '通用范围'} / {rule.role || '未限定角色'}</Typography.Paragraph>
            <Typography.Paragraph type="secondary">{rule.system_definition_id === definition.id && definition.roles.some(role => role.id === rule.role_id) ? '已登记本包角色归属' : '历史文字或其他适用范围，按需核对'}</Typography.Paragraph>
            {rule.kind === 'sharing' ? <Button onClick={() => onAdvanced(rule)}>核对共享角色</Button> : <Select aria-label={`映射角色：${rule.name}`} allowClear placeholder="明确选择本包角色" style={{ width: '100%' }} value={roles[rule.id]}
              options={definition.roles.map(role => ({ value: role.id, label: role.name }))} onChange={id => { setRoles(previous => ({ ...previous, [rule.id]: id ?? '' })); if (!id) setSelected(previous => previous.filter(key => key !== rule.id)); invalidate(); }} />}
            {!roles[rule.id] && roleSuggestion(rule, definition) ? <Typography.Text type="secondary">同名或原 ID 对应：{roleSuggestion(rule, definition)?.name}；请核对后选择</Typography.Text> : null}
            {rule.system_definition_id && rule.system_definition_id !== definition.id ? <Alert type="warning" title="当前关联其他系统；确认后新修订将改变适用范围" /> : null}
          </> : '原关系不可用' },
          { title: '数量与原文依据', render: (_, { current: rule }) => rule ? <>
            <Typography.Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开原依据' }}>{rule.evidence}</Typography.Paragraph>
            {rule.kind === 'accessory' ? <><div>{quantityDescription(rule)}</div><div>候选 {rule.target_variant_ids.length} 个 · 数量<Status value={rule.quantity_review === 'confirmed' ? 'confirmed' : 'unknown'} /></div>
              <Typography.Paragraph>{rule.quantity_evidence || '数量依据尚未单独确认'}</Typography.Paragraph><Button onClick={() => setQuantity(rule)}>核对数量与原文</Button></> : '不涉及配套数量'}
          </> : '—' },
          { title: '固定引用', width: 170, render: (_, row) => packages.filter(p => p.members.some(m => m.id === row.fixed.id)).map(p => <div key={p.id}>{p.name} · v{p.members.find(m => m.id === row.fixed.id)?.revision}</div>) },
        ]} />
      <Input aria-label="归属核对维护人" placeholder="本次归属核对维护人" value={actor} onChange={e => { setActor(e.target.value); invalidate(); }} />
      <Input.TextArea aria-label="归属核对依据" placeholder="为什么这些历史关系对应所选系统和角色；此处不确认数量或兼容性" value={evidence} onChange={e => { setEvidence(e.target.value); invalidate(); }} />
      <Space><Button disabled={!selected.length} loading={bulk.isPending} onClick={() => bulk.mutate(false)}>预览归属修改</Button><Button type="primary" disabled={!preview || bulk.isPending} onClick={() => bulk.mutate(true)}>确认整批归属</Button></Space>
      {preview ? <Alert type="warning" title={`即将修改 ${preview.items.length} 条关系的系统与角色`} description={<ul>{preview.items.map(item => { const old = knowledge.find(k => k.id === item.id)!; return <li key={item.id}>{old.name}：{old.system || '通用'} / {old.role || '未限定'} → {item.payload.system} / {item.payload.role}；关系和数量确认状态保留</li>; })}</ul>} /> : null}
    </Space></ConfigProvider>
  </Drawer>{quantity ? <QuantityReviewDialog rule={quantity} onClose={() => { setQuantity(undefined); invalidate(); }} /> : null}
  {editPackage ? <KnowledgePackageEditor initial={bundle} busy={savePackage.isPending} onClose={() => setEditPackage(false)} onSave={value => savePackage.mutate(value)} /> : null}</>;
}
