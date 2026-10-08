import { Button, Space, Table, Tag, Typography } from 'antd';

export interface KnowledgeGap {
  id: string; code: string; message: string; scenario: string;
  object_id: string; object_revision: number; missing_fields: string[]; maintenance_url: string;
}

export function KnowledgeGapList({ gaps }: { gaps: KnowledgeGap[] }) {
  return <Table rowKey="id" size="small" showHeader={false} dataSource={gaps}
    pagination={gaps.length > 10 ? { pageSize: 10 } : false} columns={[
      { render: (_, gap) => <Space direction="vertical" size={2}>
        <Space>{gap.message} {gap.scenario === 'shared' ? <Tag>仅共用部署</Tag> : null}</Space>
        <Typography.Text type="secondary">依据修订 v{gap.object_revision}</Typography.Text>
      </Space> },
      { width: 120, align: 'right', render: (_, gap) => <Button href={gap.maintenance_url}>定位维护</Button> },
    ]} />;
}
