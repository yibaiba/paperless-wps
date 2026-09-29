import { KnowledgeBatchDialog } from "./KnowledgeBatchDialog";
import { useSearchParams } from "react-router-dom";
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Collapse, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../../shared/api';
import { ROOT, Status, useKnowledge, useVariants } from '../shared';
import type { Knowledge, KnowledgePackage } from '../types';
import { configurationKeys } from '../queryKeys';
import { KnowledgeEditor, normalizeKnowledge } from '../KnowledgeEditor';
import { useDefinitions } from './useDefinitions';
import { SystemKnowledgeWorkbench } from './SystemKnowledgeWorkbench';

import { requiredRoleLabel } from "../projects/definitionSelection";
import { PackageReadiness } from "./PackageReadiness";
import { KnowledgeReconciliation } from './KnowledgeReconciliation';

const labels = { suitability: '适用候选', accessory: '配套需求', sharing: '共享条件' };
export function SystemVersionWorkbench() {
  const definitions = useDefinitions(), knowledge = useKnowledge(), variants = useVariants();
  const packages = useQuery({ queryKey: ["configuration", "knowledge-packages"], queryFn: () => api<KnowledgePackage[]>(ROOT + "/knowledge-packages") });
  const [params] = useSearchParams();
  const [systemId, setSystemId] = useState<string | undefined>(params.get("system") || undefined), [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<Knowledge>(), [batchMode, setBatchMode] = useState<'copy' | 'edit'>();
  const [reconcilingId, setReconcilingId] = useState<string>();
  const reconciling = packages.data?.find(p => p.id === reconcilingId);
  const active = definitions.data?.definitions.find((d) => d.id === systemId);
  const client = useQueryClient(), { message } = App.useApp();
  const packageRuleIds = useMemo(() => new Set((packages.data ?? []).filter((p) => p.system_definition_id === systemId).flatMap((p) => p.members.map((m) => m.id))), [packages.data, systemId]);
  const rules = useMemo(() => (knowledge.data ?? []).filter((k) => !active || packageRuleIds.has(k.id) || k.system_definition_id === active.id || [active.name, ...active.legacy_names].includes(k.system)
    || k.shared_role_refs?.some((r) => r.system_definition_id === active.id)), [knowledge.data, active, packageRuleIds]);
  const save = useMutation({ mutationFn: (value: Knowledge) => api(ROOT + '/knowledge/' + editing!.id, {
    method: 'PUT', body: JSON.stringify({ expected_revision: editing!.revision, payload: normalizeKnowledge(value) }) }),
    onSuccess: () => { client.invalidateQueries({ queryKey: configurationKeys.knowledge }); setEditing(undefined); }, onError: (e) => message.error(e.message) });
  const referenced = new Set(rules.flatMap((k) => [...k.selector.variant_ids, ...k.target_variant_ids]));
  const sourceVariants = variants.data?.filter((v) => referenced.has(v.id)) ?? [];
  return <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
    <Alert type="info" title="按系统版本核对整套知识" description="适用、需要配套、候选、数量和共享分别核对。知识包尚未发布或数量未确认时，项目仍会显示资料不足。" />
    {(definitions.error || knowledge.error || variants.error || packages.error) ? <Alert type="error" title={(definitions.error || knowledge.error || variants.error || packages.error)?.message} /> : null}
    <Select aria-label="维护系统版本" allowClear placeholder="选择系统版本" value={systemId} onChange={(value) => { setSystemId(value); setSelected([]); }} style={{ width: 440 }} options={definitions.data?.definitions.map((d) => ({ value: d.id, label: d.name }))} />
    {active ? <Card title={`${active.name} · 角色与知识覆盖`}>
      <Space wrap><Status value={active.status} />{active.roles.map((role) => <Tag key={role.id}>{role.name} · {requiredRoleLabel(role, active.status)}</Tag>)}</Space>
      <Typography.Paragraph ellipsis={{ rows: 2, expandable: true, symbol: "展开资料依据" }}>{active.evidence}</Typography.Paragraph>
      {packages.data?.filter((p) => p.system_definition_id === active.id).map((p) => <div key={p.id}>{p.name} · {p.branch} · {p.status === "published" ? "已发布" : "草稿"} · {p.members.length} 条固定修订 · {p.coverage.length} 项覆盖结论 <Button onClick={() => setReconcilingId(p.id)}>核对归属与数量</Button></div>)}
      {!definitions.data?.packages.some((p) => p.system_definition_id === active.id) ? <Alert type="warning" title="尚无已发布知识包，系统知识覆盖不能判为完整" /> : null}
    </Card> : null}
    {active ? packages.data?.filter(p => p.system_definition_id === active.id).map(p => <PackageReadiness key={p.id} bundle={p} knowledge={knowledge.data ?? []} definitionRevision={active.revision} onEdit={setEditing} />) : null}
    <Card title={`关系与资料缺口 · ${rules.length} 条`} extra={<Space><Button disabled={!selected.length} onClick={() => setBatchMode("edit")}>批量维护共同条件</Button><Button disabled={!selected.length} onClick={() => setBatchMode("copy")}>批量复制为待核对草稿</Button></Space>}>
      <Table<Knowledge> rowKey="id" dataSource={rules} loading={knowledge.isPending} scroll={{ x: 1050 }}
        rowSelection={{ selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]) }} columns={[
          { title: '关系 / 角色', render: (_, k) => <><strong>{k.name}</strong><div>{labels[k.kind]} · {k.role || '角色待映射'}</div></> },
          { title: '关系确认', render: (_, k) => <Status value={k.status} /> },
          { title: '候选配置', render: (_, k) => k.kind === 'accessory' ? `${k.target_variant_ids.length} 个${k.target_variant_ids.length ? '' : ' · 待补'}` : `${k.selector.variant_ids.length} 个 / 类别系列条件` },
          { title: '数量依据', render: (_, k) => k.kind === 'accessory' ? <><Status value={k.quantity_review === 'confirmed' ? 'confirmed' : 'unknown'} /><div>{k.quantity_evidence || '缺少确认依据'}</div></> : '不适用' },
          { title: '环境 / 共用', render: (_, k) => <>{k.conditions.length} 项条件{k.kind === 'sharing' ? <div>共用依据：<Status value={k.status} /></div> : null}</> },
          { title: '缺失项', render: (_, k) => (k.missing_fields ?? []).join('、') || (k.status === 'draft' ? '关系尚待确认' : '查看适用范围与依据') },
          { title: '维护', render: (_, k) => <Button onClick={() => setEditing(k)}>核对依据与条件</Button> },
        ]} />
    </Card>
    <Collapse items={[{ key: 'sources', label: `关联产品及原文依据 · ${sourceVariants.length} 个配置`, children: sourceVariants.map((v) => <Card key={v.id} size="small" title={`${v.product.model} · ${v.name}`}>
      {v.source_details?.map((s) => <Typography.Paragraph key={s.id} style={{ whiteSpace: 'pre-wrap' }}>{s.sheet} 第 {s.row} 行：{s.specification}\n{s.note}</Typography.Paragraph>)}
    </Card>) }, { key: 'definitions', label: '维护角色定义与发布知识包', children: <SystemKnowledgeWorkbench /> }]} />
    {editing ? <KnowledgeEditor initial={editing} onSave={(value) => save.mutate(value)} busy={save.isPending} onClose={() => setEditing(undefined)} /> : null}
    {batchMode ? <KnowledgeBatchDialog rules={rules.filter((k) => selected.includes(k.id))} definition={active} mode={batchMode} onClose={() => { setBatchMode(undefined); setSelected([]); }} /> : null}
    {reconciling ? <KnowledgeReconciliation key={`reconcile:${reconciling.id}`} bundle={reconciling} knowledge={knowledge.data ?? []} packages={packages.data ?? []} onClose={() => setReconcilingId(undefined)} onAdvanced={rule => { setReconcilingId(undefined); setEditing(rule); }} /> : null}
  </Space>;
}
