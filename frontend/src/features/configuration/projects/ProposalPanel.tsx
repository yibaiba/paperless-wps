import { useRef, useState } from 'react';
import { Alert, Button, Checkbox, Drawer, Empty, Select, Space, Table, Tabs, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import type { Checked } from '../types';
import { post, type Workspace } from './drafts/transport';
import type { Operation } from './drafts/operations';

interface Option { id: string; status: 'pass' | 'partial' | 'conflict'; standard: boolean; device_count: number; question_count: number; total: string | null; removal_candidates: string[] }
interface Proposal { option_count: number; proposal_id: string; fingerprint: string; draft_id: string; draft_revision: number; deployment: string; option: Option | null; next_offset: number | null; exhausted: boolean; stale?: boolean }
interface SavedProposal extends Proposal { option_count: number }
interface Page { items: Record<string, unknown>[]; total: number; stale?: boolean }
interface Props {
  disabled: boolean; readyWorkspace: () => Promise<Workspace>;
  execute: (operations: Operation[]) => Promise<Checked>; onApply: (checked: Checked) => void;
}
const labels = { pass: '通过已知检查', partial: '部分生成 · 资料不足', conflict: '明确条件冲突' };

export function ProposalPanel({ disabled, readyWorkspace, execute, onApply }: Props) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [history, setHistory] = useState<SavedProposal[]>([]), [historyOffset, setHistoryOffset] = useState(0), [historyTotal, setHistoryTotal] = useState(0);
  const [historyDraft, setHistoryDraft] = useState('');
  const [deployment, setDeployment] = useState('independent');
  const [proposal, setProposal] = useState<Proposal>(), [options, setOptions] = useState<Option[]>([]);
  const [selected, setSelected] = useState<Option>(), [view, setView] = useState('proposal_lines');
  const [page, setPage] = useState(1), [removeIds, setRemoveIds] = useState<string[]>([]);
  const pending = useRef<{ request: Record<string, unknown>; extend: boolean } | undefined>(undefined);
  const details = useQuery({ queryKey: ['proposal-detail', proposal?.proposal_id, selected?.id, view, page],
    enabled: open && !!proposal && !!selected,
    queryFn: () => post<Page>('/list-tools/list_get', { draft_id: proposal!.draft_id, proposal_id: proposal!.proposal_id, option_id: selected!.id, view, offset: (page - 1) * 20, limit: 20 }),
  });
  const loadHistory = async (offset = 0) => {
    setBusy(true); setError('');
    try {
      const workspace = await readyWorkspace(); setHistoryDraft(workspace.id);
      const result = await post<{items: SavedProposal[]; total: number}>('/list-tools/list_get', { draft_id: workspace.id, view: 'proposals', offset, limit: 20 });
      setHistory(result.items); setHistoryOffset(offset); setHistoryTotal(result.total);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const restoreProposal = async (id: string) => {
    setBusy(true); setError('');
    try {
      const saved = history.find(item => item.proposal_id === id)!;
      const result = await post<Proposal & { items: Option[] }>('/list-tools/list_get', { draft_id: historyDraft, proposal_id: id, view: 'proposals', offset: 0, limit: 20 });
      setProposal(result); setOptions(result.items); setSelected(result.items[0]); setDeployment(saved.deployment);
      setRemoveIds([]); setPage(1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const loadSavedOptions = async () => {
    if (!proposal) return;
    setBusy(true); setError('');
    try {
      const result = await post<{items: Option[]}>('/list-tools/list_get', { draft_id: proposal.draft_id, proposal_id: proposal.proposal_id, view: 'proposals', offset: options.length, limit: 20 });
      setOptions(previous => [...previous, ...result.items]);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const generate = async (extend = false) => {
    setBusy(true); setError('');
    try {
      if (!pending.current) {
        const workspace = await readyWorkspace();
        pending.current = { extend, request: { draft_id: workspace.id, expected_revision: workspace.revision, operation_id: crypto.randomUUID(), deployment,
          ...(extend && proposal ? { proposal_id: proposal.proposal_id, option_offset: proposal.next_offset } : {}) } };
      }
      const result = await post<Proposal>('/list-tools/list_plan', pending.current.request);
      const wasExtend = pending.current.extend; pending.current = undefined;
      setProposal(result); setRemoveIds([]); setPage(1);
      if (result.option) { const option = result.option; setSelected(option); setOptions(previous => wasExtend ? [...previous.filter(item => item.id !== option.id), option] : [option]); }
      else if (!wasExtend) { setOptions([]); setSelected(undefined); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    if (!proposal || !selected) return;
    setBusy(true); setError('');
    try {
      const result = await execute([{ action: 'proposal_apply', proposal_id: proposal.proposal_id, option_id: selected.id, fingerprint: proposal.fingerprint, remove_device_ids: removeIds }]);
      onApply(result); setOpen(false); setProposal(undefined); setOptions([]); setSelected(undefined);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };
  return <><Button disabled={disabled} onClick={() => setOpen(true)}>按需求生成方案</Button>
    <Drawer open={open} size={1000} title="需求驱动方案" onClose={() => !busy && setOpen(false)} extra={<Button type="primary" disabled={disabled || !selected || busy || details.isFetching || !!proposal?.stale || !!details.data?.stale} onClick={() => void apply()}>整批采用所选方案</Button>}>
      <Alert type="info" showIcon title="提案不会修改清单" description="根据已发布资料生成；选择采用后进入同一工作草稿，可撤销。资料不足不代表已认证，缺价不代表零元。" />
      <Space wrap style={{ marginBlock: 16 }}>
        <Select aria-label="部署方式" value={deployment} disabled={busy || !!pending.current} style={{ width: 210 }} onChange={value => { setDeployment(value); setProposal(undefined); setOptions([]); setSelected(undefined); }} options={[{ value: 'independent', label: '独立部署标准方案' }, { value: 'shared', label: '比较共享部署分支' }]} />
        <Button type="primary" loading={busy} disabled={disabled} onClick={() => void generate()}>{pending.current ? '用原请求重试生成' : '根据当前需求生成'}</Button>
        <Button disabled={disabled || busy || !proposal || proposal.exhausted} onClick={() => void generate(true)}>读取下一替代方案</Button>
        <Button disabled={busy || !!pending.current} onClick={() => void loadHistory()}>读取已保存提案</Button>
        {proposal?.exhausted ? <Typography.Text type="secondary">已读取全部可用分支</Typography.Text> : null}
      </Space>
      {history.length ? <Space wrap style={{ marginBottom: 12 }}><Select aria-label="恢复已保存提案" placeholder="选择历史提案" style={{ width: 480 }} disabled={busy} onChange={id => void restoreProposal(id)} options={history.map(item => ({ value: item.proposal_id, label: `草稿修订 ${item.draft_revision} · ${item.deployment === 'shared' ? '共享' : '独立'}部署 · 已生成 ${item.option_count} 个分支 · ${item.proposal_id.slice(0, 8)}` }))} /><Button disabled={!historyOffset || busy} onClick={() => void loadHistory(historyOffset - 20)}>上一页提案</Button><Button disabled={historyOffset + 20 >= historyTotal || busy} onClick={() => void loadHistory(historyOffset + 20)}>下一页提案</Button></Space> : null}
      {error ? <Alert type="error" showIcon title={error} action={pending.current ? <Button onClick={() => { pending.current = undefined; setError(''); }}>放弃请求并重新生成</Button> : undefined} /> : null}
      {options.length ? <Select aria-label="选择提案方案" style={{ width: '100%', marginBottom: 12 }} value={selected?.id} onChange={id => { setSelected(options.find(o => o.id === id)); setRemoveIds([]); setPage(1); }} options={options.map((option, index) => ({ value: option.id, label: `${option.standard ? index === 0 ? '标准分支' : '替代分支' : '待确认推荐顺序的分支'} ${index + 1} · ${option.device_count} 项 · ${labels[option.status]}` }))} /> : <Empty description="先建立房间、系统与需求，再生成提案" />}
      {proposal && options.length < proposal.option_count ? <Button disabled={busy} onClick={() => void loadSavedOptions()}>读取更多已生成分支</Button> : null}
      {selected ? <>
        <Space><Tag>{labels[selected.status]}</Tag><Typography.Text>待确认 {selected.question_count} 项</Typography.Text><Typography.Text>{selected.total == null ? '完整报价尚待确认' : `报价 ¥${selected.total}`}</Typography.Text></Space>
        {selected.removal_candidates.length ? <div><Typography.Paragraph>以下原生成设备已无用途，默认保留。需要移除时明确选择：</Typography.Paragraph><Checkbox.Group options={selected.removal_candidates} value={removeIds} onChange={values => setRemoveIds(values as string[])} /></div> : null}
        {details.error ? <Alert type="error" title={details.error.message} /> : null}
        {details.data?.stale ? <Alert type="warning" title="草稿已变化，此提案已过期，请重新生成" /> : null}
        <Tabs activeKey={view} onChange={value => { setView(value); setPage(1); }} items={[
          { key: 'proposal_lines', label: '建议清单' }, { key: 'proposal_questions', label: '待确认事项' }, { key: 'proposal_decisions', label: '生成依据' }, { key: 'proposal_changes', label: '改单差异' },
        ]} />
        <Table size="small" loading={details.isFetching} dataSource={details.data?.items ?? []} rowKey={(_, index) => String((page - 1) * 20 + (index ?? 0))}
          pagination={{ current: page, pageSize: 20, total: details.data?.total ?? 0, showSizeChanger: false, onChange: setPage }} columns={view === 'proposal_lines' ? [
            { title: '产品', render: (_, row) => String(row.name ?? row.model ?? row.device_id) }, { title: '部署数量', dataIndex: 'quantity' }, { title: '用途 / 来源', render: (_, row) => <Typography.Paragraph style={{ margin: 0 }}>{Array.isArray(row.consumers) ? row.consumers.map((item: Record<string, unknown>) => [item.system, item.role].filter(Boolean).join(' / ')).join('；') : String(row.source_name ?? row.model ?? '见产品与来源详情')}</Typography.Paragraph> },
          ] : view === 'proposal_questions' ? [
            { title: '由谁补充', width: 130, render: (_, row) => <Tag>{row.recipient === 'customer' ? '客户 / 项目' : '内部维护者'}</Tag> }, { title: '待确认事项', dataIndex: 'message' }, { title: '需要补充', render: (_, row) => String(row.missing_fields) },
          ] : [{ title: view === 'proposal_decisions' ? '采用依据与数量计算' : '变更前后', render: (_, row) => <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>{JSON.stringify(row, null, 2)}</Typography.Paragraph> }]} />
      </> : null}
    </Drawer>
  </>;
}
