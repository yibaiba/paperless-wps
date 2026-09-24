import { Flex, Typography } from 'antd';
import type { ReactNode } from 'react';

export function PageHeader({ title, description, actions }: {
  title: string; description: string; actions?: ReactNode;
}) {
  return <Flex className="page-heading" justify="space-between" align="center" gap={20} wrap>
    <div><Typography.Title level={2}>{title}</Typography.Title>
      <Typography.Paragraph type="secondary">{description}</Typography.Paragraph></div>
    {actions}
  </Flex>;
}
