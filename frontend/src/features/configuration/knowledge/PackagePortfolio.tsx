import { Alert, Card, Table, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';

import { api } from '../../../shared/api';
import { ROOT } from '../shared';

type Scenario = { status: 'supported' | 'partial' | 'missing'; issue_count: number };
type Portfolio = {
  id: string;
  name: string;
  status: 'draft' | 'published';
  definition_status: 'draft' | 'confirmed';
  scenarios: { independent: Scenario; shared: Scenario };
  independent_content_ready: boolean;
  shared_content_ready: boolean;
  generation_roles: { supported: number; partial: number; missing: number; with_confirmed_candidates: number; total: number };
  confirmed_relations: number;
  relation_count: number;
  blocker_fields: string[];
  issue_count: number;
};

const readiness = (ready: boolean, scenario: Scenario) => (
  <Tag color={ready && scenario.status === 'supported' ? 'green' : scenario.status === 'partial' ? 'orange' : 'red'}>
    {ready ? scenario.status === 'supported' ? '已发布支持' : '内容已齐，待发布' : `阻塞 ${scenario.issue_count} 项`}
  </Tag>
);

export function PackagePortfolio() {
  const query = useQuery({
    queryKey: ['configuration', 'knowledge-packages', 'readiness-summary'],
    queryFn: () => api<Portfolio[]>(`${ROOT}/knowledge-packages/readiness-summary`),
  });
  if (query.error) return <Alert type="error" title="六套资料包状态读取失败" description={query.error.message} />;
  return <Card title="六套系统资料包 · 生成范围">
    <Table<Portfolio> rowKey="id" size="small" loading={query.isPending} dataSource={query.data} pagination={false}
      columns={[
        { title: '资料包', dataIndex: 'name', render: (name, row) => <><strong>{name}</strong><div><Tag>{row.status === 'published' ? '已发布' : '草稿'}</Tag><Tag>{row.definition_status === 'confirmed' ? '角色已确认' : '角色待确认'}</Tag></div></> },
        { title: '独立部署', render: (_, row) => readiness(row.independent_content_ready, row.scenarios.independent) },
        { title: '共享部署', render: (_, row) => readiness(row.shared_content_ready, row.scenarios.shared) },
        { title: '可生成角色', render: (_, row) => `${row.generation_roles.supported} 完整 / ${row.generation_roles.with_confirmed_candidates} 有候选 / ${row.generation_roles.total} 总数` },
        { title: '关系', render: (_, row) => `${row.confirmed_relations} 已确认 / ${row.relation_count} 总数` },
        { title: '主要阻塞字段', render: (_, row) => <Typography.Text ellipsis={{ tooltip: row.blocker_fields.join('、') }}>{row.blocker_fields.slice(0, 4).join('、') || '无'}</Typography.Text> },
      ]} />
  </Card>;
}
