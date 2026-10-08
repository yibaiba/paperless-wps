import { Alert, Button, Card, Space, Table } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useRef, useState, type ReactNode } from 'react';
import { api } from '../../../../shared/api';
import type { Workspace } from './transport';

export function DraftRecovery({ projectId, children }: { projectId: string; children: (workspace?: Workspace) => ReactNode }) {
  const [params, setParams] = useSearchParams(), id = params.get('draft');
  const entered = useRef<{ workspace?: Workspace; id?: string | null } | null>(null);
  if (entered.current?.id && entered.current.id !== id) entered.current = null;
  if (entered.current && !entered.current.id && id) entered.current.id = id;
  const [dismissed, setDismissed] = useState(false);
  const query = useQuery({ queryKey: ['work-drafts', projectId], refetchOnMount: 'always', queryFn: () => api<(Workspace & { origin: string })[]>('/work-drafts?project_id=' + encodeURIComponent(projectId)) });
  const recovery = useQuery({ queryKey: ['work-draft', id], enabled: !!id && !entered.current, staleTime: 0, refetchOnMount: 'always',
    queryFn: () => api<Workspace>('/work-drafts/' + encodeURIComponent(id!)) });
  if (entered.current) return children(entered.current.workspace);
  if (recovery.error) return <Alert type="error" title={recovery.error.message} />;
  if (id && (!recovery.data || recovery.isPending || recovery.isFetching)) return <Card loading />;
  if (recovery.data && recovery.data.project_id !== projectId) return <Alert type="error" title="工作草稿不属于当前项目" />;
  if (id) { entered.current = { workspace: recovery.data, id }; return children(recovery.data); }
  if ((query.isPending || query.isFetching) && !dismissed) return <Card loading />;
  if (!dismissed && query.error) return <Alert type="error" title={query.error.message} action={<Button onClick={() => query.refetch()}>重试读取草稿</Button>} />;
  if (!dismissed && query.data?.length) return <Card title="发现可恢复的工作草稿">
    <Alert type="info" title="请选择要继续的草稿，或从已保存项目建立独立草稿。不会自动合并其他窗口或 Agent 的修改。" />
    <Table rowKey="id" size="small" showHeader={false} pagination={false} dataSource={query.data} columns={[
      { render: (_, item) => <Space>{item.origin === 'web' ? '网页' : 'Agent'} · 基线 v{item.base_revision} · 草稿 r{item.revision} · {new Date(item.updated_at).toLocaleString()}</Space> },
      { width: 120, align: 'right', render: (_, item) => <Button onClick={() => setParams({ draft: item.id })}>恢复此草稿</Button> },
    ]} />
    <Button onClick={() => setDismissed(true)}>从已保存版本开始</Button>
  </Card>;
  entered.current = {};
  return children();
}
