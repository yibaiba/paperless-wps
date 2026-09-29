import { BulkPrices } from "./BulkPrices";
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Drawer, Empty, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../../../shared/api';
import { configurationKeys } from '../../queryKeys';
import { useVariants } from '../../shared';
import { CreateUpdate } from './CreateUpdate';
import { RowDecision } from './RowDecision';
import { type Batch, type Preview, type UpdateRow, updateRoot, classifications, actions } from './types';
export function UpdateWorkbench({ onClose }: { onClose: () => void }) {
  const client = useQueryClient(), variants = useVariants();
  const [bulk, setBulk] = useState(false);
  const [creating, setCreating] = useState(false), [id, setId] = useState<string>();
  const [page, setPage] = useState(1), [selected, setSelected] = useState<string[]>([]), [editing, setEditing] = useState<UpdateRow>();
  const [preview, setPreview] = useState<Preview>(), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [applyId, setApplyId] = useState('');
  const batches = useQuery({ queryKey: ['catalog-updates'], queryFn: () => api<Batch[]>(updateRoot) });
  const batch = useQuery({ queryKey: ['catalog-updates', id, page], enabled: !!id,
    queryFn: () => api<Batch>(`${updateRoot}/${id}?offset=${(page - 1) * 30}&limit=30`) });
  async function refresh() { await client.invalidateQueries({ queryKey: ['catalog-updates'] }); await client.invalidateQueries({ queryKey: configurationKeys.all }); await client.invalidateQueries({ queryKey: ['imports'] }); }
  async function prepare() {
    if (!batch.data) return;
    setBusy(true); setError('');
    try { setPreview(await api<Preview>(`${updateRoot}/${id}/preview`, { method: 'POST', body: JSON.stringify({ expected_revision: batch.data.revision, row_ids: selected }) })); setApplyId(crypto.randomUUID()); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function apply() {
    if (!batch.data || !preview) return;
    setBusy(true); setError('');
    try { await api(`${updateRoot}/${id}/apply`, { method: 'POST', body: JSON.stringify({ expected_revision: batch.data.revision, row_ids: selected, fingerprint: preview.fingerprint, operation_id: applyId }) }); setPreview(undefined); setSelected([]); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <Drawer open size="90%" title="更新产品与价格" onClose={onClose}>
    <Space orientation="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="info" title="上传或人工维护 → 核对归属与差异 → 预览发布 → 项目选择采用" description="保存行结论仅更新草稿。只有明确选择的行才发布；旧项目和原始 Excel 不会变化。" />
      <Space wrap><Button type="primary" onClick={() => setCreating(true)}>建立更新草稿</Button>
        <Select aria-label="恢复更新草稿" placeholder="恢复已有更新草稿" value={id} style={{ minWidth: 340 }} options={batches.data?.map(b => ({ value: b.id, label: `${b.name} · 待处理 ${(b.counts?.pending ?? 0) + (b.counts?.partial ?? 0) + (b.counts?.deferred ?? 0)}` }))} onChange={value => { setId(value); setPage(1); setSelected([]); }} />
        <Button disabled={!selected.length || busy} onClick={() => setBulk(true)}>批量核对价格</Button>
        <Button disabled={!selected.length || busy} loading={busy} onClick={() => void prepare()}>预览所选变更（{selected.length}）</Button>
      </Space>
      {error || batches.error || batch.error ? <Alert type="error" title={error || batches.error?.message || batch.error?.message} /> : null}
      {!id ? <Empty description="建立或恢复更新草稿后开始核对" /> : <Table<UpdateRow> rowKey="id" loading={batch.isFetching} dataSource={batch.data?.rows} pagination={{ current: page, pageSize: 30, total: batch.data?.total, onChange: value => { setPage(value); setSelected([]); }, showSizeChanger: false }}
        rowSelection={{ selectedRowKeys: selected, onChange: keys => setSelected(keys.map(String)), getCheckboxProps: r => ({ disabled: r.state === 'applied' }) }}
        columns={[
          { title: '产品 / 位置', render: (_, r) => <><strong>{r.source?.model || variants.data?.find(v => v.id === r.variant_id)?.product.model}</strong><div>{r.source ? `${r.source.sheet} · ${r.source.row} 行 · ${r.source.name}` : variants.data?.find(v => v.id === r.variant_id)?.name}</div></> },
          { title: '差异', render: (_, r) => <Tag>{classifications[r.classification]}</Tag> },
          { title: '候选配置', render: (_, r) => r.candidates.length ? r.candidates.map(c => c.name).join('、') : (r.variant_id ? '已指定配置' : '需建立或人工指定') },
          { title: '处理结论', render: (_, r) => <>{r.decision ? actions.find(a => a.value === r.decision?.action)?.label : '未核对'}{r.pending_prices?.length ? <div>保留原状态、尚未发布：{r.pending_prices.join('、')}</div> : null}</> },
          { title: '发布状态', render: (_, r) => <Tag color={r.state === 'applied' ? 'green' : 'gold'}>{({ applied: '已发布', partial: '部分发布，继续核对', deferred: '明确待核对', pending: '草稿' } as Record<string, string>)[r.state]}</Tag> },
          { title: '操作', render: (_, r) => <Button disabled={r.state === 'applied'} onClick={() => setEditing(r)}>核对 / 编辑</Button> },
        ]} />}
    </Space>
    {bulk && batch.data ? <BulkPrices batch={batch.data} rows={batch.data.rows.filter(r => selected.includes(r.id))} onClose={() => setBulk(false)} onSaved={() => void refresh()} /> : null}
    {creating ? <CreateUpdate onClose={() => setCreating(false)} onCreated={b => { setId(b.id); setPage(1); setCreating(false); void refresh(); }} /> : null}
    {editing && batch.data ? <RowDecision row={editing} batch={batch.data} onClose={() => setEditing(undefined)} onSaved={() => { setSelected([]); void refresh(); }} /> : null}
    <Modal open={!!preview} title="发布变更预览" width={850} onCancel={() => setPreview(undefined)} onOk={() => void apply()} confirmLoading={busy} okText="确认发布所选行">
      {error ? <Alert type="error" title={error} /> : null}
      {preview?.changes.map(c => <div key={c.row_id} style={{ marginBottom: 20 }}>
        <Typography.Text strong>{actions.find(a => a.value === c.decision.action)?.label}</Typography.Text>
        {c.decision.product ? <p>{c.decision.product.model} · {c.decision.product.name}</p> : null}
        {c.decision.variant ? <p>配置：{(c.decision.variant as { name?: string }).name}</p> : null}
        {c.prices.map(p => <p key={p.after.column}>{p.after.column}：{p.before?.state === 'inquiry' ? '待询价' : p.before?.amount ?? '无版本价格'} → {p.after.state === 'inquiry' ? '待询价' : p.after.amount}，{p.after.effective_date} 生效</p>)}
        {c.pending_prices?.length ? <p>保留原价、未发布：{c.pending_prices.join("、")}。空白 / 非数值仍需核对。</p> : null}
        {c.impact ? <p>关联范围：{c.impact.rules.length} 条搭配、{c.impact.packages.length} 个资料包、{c.impact.projects.length} 个项目。{c.decision.action === 'correct' ? '参数修正后仅此配置进入搭配复核；历史项目不变。' : ['new_product', 'new_variant'].includes(c.decision.action) ? '这是原配置的引用范围；新配置独立建立，原项目不改变。' : '原项目保留快照；价格修改不变更搭配结论。'}</p> : null}
      </div>)}
    </Modal>
  </Drawer>;
}
