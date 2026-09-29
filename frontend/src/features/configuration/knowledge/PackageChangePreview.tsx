import { useQuery } from '@tanstack/react-query';
import { Alert, Collapse, Modal, Space, Table, Typography } from 'antd';
import { api } from '../../../shared/api';
import { ROOT } from '../shared';
import type { Knowledge, KnowledgePackage, SystemDefinition } from '../types';

type Preview = { changes: { field: string; before: unknown; after: unknown }[]; relations: { id: string; before?: Knowledge; after?: Knowledge }[];
  definition: { before: SystemDefinition; after: SystemDefinition }; readiness: { summary: Record<string, number>; roles: { id: string; name: string; missing: string[] }[]; rules: { id: string; name: string; missing: string[] }[] } };
export function PackageChangePreview({ original, payload, busy, onClose, onApply }: {
  original: KnowledgePackage; payload: unknown; busy: boolean; onClose: () => void; onApply: () => void;
}) {
  const query = useQuery({ queryKey: ['configuration', 'package-preview', original.id, original.revision, payload], retry: false,
    queryFn: () => api<Preview>(`${ROOT}/knowledge-packages/${original.id}/change-preview`, { method: 'POST', body: JSON.stringify({ expected_revision: original.revision, payload }) }) });
  return <Modal open width={1000} title="整理本次变更" onCancel={onClose} onOk={onApply} okText="采用所选修订并保存" confirmLoading={busy} okButtonProps={{ disabled: !query.data || !!query.error }}>
    {query.error ? <Alert type="error" title={query.error.message} /> : null}
    {query.isPending ? <Typography.Paragraph>正在核对修订…</Typography.Paragraph> : null}
    {query.data ? <Space orientation="vertical" style={{ width: '100%' }}>
      <Alert type="info" title="仅保存本次明确选择的资料，原项目快照不变" description="发布资料版本不代表所有搭配都已确认。缺少依据的内容仍保留待办。" />
      <Typography.Text>角色定义 v{query.data.definition.before.revision} → v{query.data.definition.after.revision}</Typography.Text>
      <Table rowKey="id" pagination={false} dataSource={query.data.relations} columns={[
        { title: '关系', render: (_, r) => r.after?.name ?? r.before?.name },
        { title: '原修订', render: (_, r) => r.before ? `v${r.before.revision}` : '未引用' },
        { title: '本次采用', render: (_, r) => r.after ? `v${r.after.revision} · ${r.after.status}` : '移出本包' },
      ]} />
      <Typography.Text>角色资料缺口：{query.data.readiness.summary.roles_with_gaps} 项；关系资料缺口：{query.data.readiness.summary.rules_with_gaps} 项</Typography.Text>
      <Collapse items={[{ key: 'fields', label: '字段及覆盖结论差异', children: query.data.changes.map(c => <div key={c.field}><Typography.Text strong>{({ name: '名称', branch: '环境分支', status: '发布状态', members: '引用关系', coverage: '覆盖结论', definition_revision: '角色定义修订', actor: '维护人', evidence: '维护依据' } as Record<string, string>)[c.field] ?? c.field}</Typography.Text><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify({ 原值: c.before, 新值: c.after }, null, 2)}</pre></div>) },
        { key: 'readiness', label: '采用后的待确认事项', children: <Table rowKey="id" pagination={false} dataSource={[...query.data.readiness.roles, ...query.data.readiness.rules].filter(r => r.missing.length)} columns={[{ title: '对象', dataIndex: 'name' }, { title: '缺少什么', render: (_, r) => r.missing.join('；') }]} /> }]} />
    </Space> : null}
  </Modal>;
}
