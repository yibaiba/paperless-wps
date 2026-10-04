import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Collapse, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../../shared/api';
import type { Checked, Configuration } from '../types';
import { ROOT } from '../shared';
import { configurationKeys } from '../queryKeys';
import { BindingEditor } from './BindingEditor';
import type { CaseBinding, CaseRow, Comparison } from './types';
const labels: Record<string, string> = { matched: '已对应', alternative: '采用其他配置', not_enabled: '功能未启用', satisfied: '已有／已含满足', unknown: '资料不足', conflict: '明确冲突' };
export function ReferenceCasePanel({ configuration, checked, busy, onChange, onDevice, onRole, onReview }: { configuration: Configuration; checked?: Checked; busy: boolean; onChange: (value: Configuration) => void; onDevice: (id: string) => void; onRole: (id: string) => void; onReview: () => void }) {
  const [open, setOpen] = useState(false), [editing, setEditing] = useState<CaseRow>();
  const reference = configuration.reference_case;
  const cases = useQuery({ queryKey: configurationKeys.referenceCases, enabled: open, queryFn: () => api<{ id: string; revision: number; name: string; row_count: number }[]>(ROOT + '/reference-cases') });
  const comparison = useQuery({ queryKey: configurationKeys.caseComparison(configuration), enabled: open && !!reference && !busy,
    queryFn: () => api<Comparison>(ROOT + '/reference-cases/compare', { method: 'POST', body: JSON.stringify(configuration) }) });
  function apply(binding: CaseBinding) { if (!reference) return; onChange({ ...configuration, reference_case: { ...reference, bindings: [...reference.bindings.filter(b => b.row_id !== binding.row_id), binding] } }); setEditing(undefined); }
  return <Collapse onChange={keys => setOpen(keys.includes('reference'))} items={[{ key: 'reference', label: '与参考清单对账', children: <Space orientation="vertical" style={{ width: '100%' }}>
    <Alert type="info" title="参考清单仅作对照，当前方案依据项目需求与固定资料生成。" />
    {cases.error || comparison.error ? <Alert type="error" title={(cases.error || comparison.error)?.message} /> : null}
    <Space wrap><Select style={{ width: "100%", maxWidth: 600 }} placeholder="选择参考案例" value={reference?.id} disabled={busy} options={cases.data?.map(c => ({ value: c.id, label: `${c.name} · v${c.revision} · ${c.row_count} 项` }))}
      onChange={id => { const selected = cases.data!.find(c => c.id === id)!; onChange({ ...configuration, reference_case: { id, revision: selected.revision, bindings: [] } }); }} />
      {reference && <><Tag>项目固定 v{reference.revision}</Tag><Button disabled={busy} onClick={() => onChange({ ...configuration, reference_case: null })}>解除案例关联</Button></>}</Space>
    {reference && cases.data && cases.data.find(c => c.id === reference.id)?.revision !== reference.revision && <Alert type="info" title="案例有新修订；本项目仍使用原修订。切换案例将重新建立映射。" />}
    <Table<CaseRow> size="small" rowKey="row_id" loading={busy || comparison.isFetching} dataSource={comparison.data?.rows} pagination={{ pageSize: 10, showTotal: total => `共 ${total} 项` }} scroll={{ x: 1250 }} columns={[
      { title: '原清单', width: 240, render: (_, r) => <>{r.original.section} · {r.original.name}<div>{r.original.model} · {r.original.quantity ?? '未知'} {r.original.unit}</div></> },
      { title: '当前配置', width: 220, render: (_, r) => r.current.map(d => <div key={d.device_id}><Button type="link" onClick={() => onDevice(d.device_id)}>{d.model} · {d.name}</Button></div>) },
      { title: '部署 / 采购', width: 130, render: (_, r) => <>{r.deployed} / {r.purchase}<div>已有 {r.existing} · 已含 {r.included}</div><div>用于此行 {r.mapped_quantity ?? "待核对"}</div><div>数量差 {r.quantity_delta ?? '未知'}</div></> },
      { title: '结论与原因', render: (_, r) => <><Tag color={r.status === 'conflict' ? 'red' : r.status === 'unknown' ? 'orange' : 'blue'}>{labels[r.status]}</Tag><div>{r.reason}</div></> },
      { title: '处理', width: 150, render: (_, r) => <Space orientation="vertical"><Button disabled={busy} onClick={() => setEditing(r)}>建立／修改映射</Button>{r.binding?.requirement_ids.map(id => <Button key={id} onClick={() => onRole(id)}>角色选型</Button>)}<Button onClick={onReview}>配套／供货／价格</Button></Space> },
    ]} expandable={{ expandedRowRender: r => <><Typography.Paragraph>{r.evidence}</Typography.Paragraph>{r.original.questions.map((q, i) => <div key={i}>待核对：{q}</div>)}{r.issues.map((issue, i) => <div key={i}>{issue.status}：{issue.message || issue.code}</div>)}{r.original.evidence_refs.map((e, i) => <Typography.Paragraph key={i} style={{ whiteSpace: 'pre-wrap' }}>{e.locator} · v{e.material_revision}：{e.quote}</Typography.Paragraph>)}</> }} />
    {!!comparison.data?.additional.length && <Alert type="info" title={`另有 ${comparison.data.additional.length} 项设备未对应原案例`} description={comparison.data.additional.map(d => `${d.model} ${d.quantity}${d.unit}（${d.source.sheet ?? '固定来源'}）`).join('；')} />}
    {editing && <BindingEditor row={editing} configuration={configuration} checked={checked} onApply={apply} onClose={() => setEditing(undefined)} />}
  </Space> }]} />;
}
