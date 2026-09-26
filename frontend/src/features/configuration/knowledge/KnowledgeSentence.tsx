import { Card, Typography } from "antd";

export function KnowledgeSentence({ summary }: { summary: string }) {
  return (
    <Card size="small" title="系统将这样理解">
      <Typography.Text strong>{summary}</Typography.Text>
    </Card>
  );
}
