import { Button, List, Tag } from 'antd';

export interface KnowledgeGap {
  id: string; code: string; message: string; scenario: string;
  object_id: string; object_revision: number; missing_fields: string[]; maintenance_url: string;
}

export function KnowledgeGapList({ gaps }: { gaps: KnowledgeGap[] }) {
  return <List dataSource={gaps} pagination={gaps.length > 10 ? { pageSize: 10 } : false}
    renderItem={gap => <List.Item key={gap.id} actions={[
      <Button key="maintain" href={gap.maintenance_url}>定位维护</Button>,
    ]}>
      <List.Item.Meta title={<>{gap.message} {gap.scenario === 'shared' ? <Tag>仅共用部署</Tag> : null}</>}
        description={`依据修订 v${gap.object_revision}`} />
    </List.Item>} />;
}
