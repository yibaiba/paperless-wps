import { Collapse, Space, Table } from 'antd';
import type { BusinessChange } from '../types';

const labels: Record<string, string> = {
  devices: '部署设备', requirements: '角色用途', systems: '系统需求', rooms: '房间',
  supply_allocations: '供货分配', accessory_allocations: '配套分配', included_allocations: '已含内容抵扣',
  decision_runtime: '决策方式', decision_bundle_id: '固定资料版本', quotation: '报价',
};

export function describeChange(value: unknown): string {
  if (value == null) return '无';
  if (typeof value !== 'object') return ({ 'python-v3': '历史 Python 判断', 'zen-v1': 'ZEN 统一决策 v1' } as Record<string, string>)[String(value)] ?? String(value);
  const item = value as Record<string, unknown>;
  const source = typeof item.source === 'string' ? ({ purchase: '本次采购', existing: '客户已有', unknown: '供货待确认' }[item.source] ?? item.source) : '';
  if (item.name || item.quantity != null) return [item.name, item.model, item.quantity != null ? `数量 ${item.quantity}` : '', source].filter(Boolean).join(' · ');
  if (item.role) return String(item.role);
  return '字段与依据变更（展开查看）';
}

export function BusinessChangeTable({ changes, loading, page }: {
  changes?: BusinessChange[]; loading: boolean;
  page?: { current: number; total: number; onChange: (value: number) => void };
}) {
  return <Table<BusinessChange> rowKey={r => `${r.kind}:${r.id}`} size="small" loading={loading} dataSource={changes}
    pagination={page ? { ...page, pageSize: 20, showSizeChanger: false } : undefined}
    expandable={{ expandedRowRender: change => <Collapse items={[{ key: 'details', label: '完整字段变化与依据', children: <Space align="start" style={{ maxWidth: '100%', overflow: 'auto' }}><pre>{JSON.stringify(change.before, null, 2)}</pre><pre>{JSON.stringify(change.after, null, 2)}</pre></Space> }]} /> }}
    columns={[
      { title: '对象', render: (_, change) => labels[change.kind] ?? change.kind },
      { title: '修改前', render: (_, change) => describeChange(change.before) },
      { title: '修改后', render: (_, change) => describeChange(change.after) },
    ]} />;
}
