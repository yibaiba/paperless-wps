import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Drawer, Form, Input, Select, Space, Tabs, Tag, Timeline, Typography } from 'antd';
import { api } from '../../shared/api';
import type { Issue, ReviewStatus } from '../../shared/types';
import { reviewColors, reviewLabels } from './reviewLabels';

interface ReviewValues { status: ReviewStatus; actor: string; note: string }

function Evidence({ issue }: { issue: Issue }) {
  return <div className="evidence-grid">{issue.evidence.map((entry, index) =>
    <Card key={`${entry.sheet}-${entry.range}-${index}`} size="small" title={`${entry.sheet} · ${entry.range}`}>
      <div className="source-text evidence-text">{entry.value || '原表为空'}</div>
    </Card>,
  )}</div>;
}

function History({ issue }: { issue: Issue }) {
  return issue.history.length ? <Timeline items={issue.history.map(entry => ({
    key: entry.id,
    content: <Space orientation="vertical" size={6}>
      <Tag color={reviewColors[entry.status]}>{reviewLabels[entry.status]}</Tag>
      <Typography.Text>{entry.actor} · {new Date(entry.created_at!).toLocaleString('zh-CN')} · 第 {entry.revision} 次处理</Typography.Text>
      <Typography.Paragraph className="source-text">{entry.note}</Typography.Paragraph>
    </Space>,
  }))} /> : <Typography.Text type="secondary">还没有处理记录。</Typography.Text>;
}

export function IssueReviewDrawer({ issue, onClose }: { issue: Issue; onClose: () => void }) {
  const [form] = Form.useForm<ReviewValues>();
  const [revision] = useState(issue.review.revision);
  const client = useQueryClient();
  const { message } = App.useApp();
  const save = useMutation({
    mutationFn: (values: ReviewValues) => api<Issue>(`/issues/${issue.id}/reviews`, {
      method: 'POST', body: JSON.stringify({ ...values, expected_revision: revision }),
    }),
    onSuccess: async () => {
      await Promise.all(['issues', 'products', 'product', 'project'].map(key =>
        client.invalidateQueries({ queryKey: [key] }),
      ));
      message.success('处理结论已保存，原始资料保留');
      onClose();
    },
    onError: () => { void client.invalidateQueries({ queryKey: ['issues'] }); },
  });
  return <Drawer title={`${issue.evidence[0]?.model} · 差异处理`} open onClose={onClose} size={820}>
    <Typography.Paragraph>{issue.description}</Typography.Paragraph>
    <Tag color={reviewColors[issue.review.status]}>{reviewLabels[issue.review.status]}</Tag>
    <Tabs className="section-gap" items={[
      { key: 'review', label: '来源与处理', children: <>
        <Evidence issue={issue} />
        <Alert className="section-gap section-bottom" type="info" showIcon
          title="结论针对本次资料差异，原始参数会继续保留。"
          description="确认配置差异不会合并产品；标记原资料有误后，仍需修订来源资料。" />
        {save.error ? <Alert className="section-bottom" type="error" showIcon title={save.error.message}
          description="如果已有更新，请关闭后重新打开查看最新记录；当前填写内容未提交。" /> : null}
        <Form form={form} layout="vertical" initialValues={{ status: issue.review.status }} onFinish={values => save.mutate(values)}>
          <Form.Item name="status" label="处理结论" rules={[{ required: true }]}>
            <Select options={Object.entries(reviewLabels).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item name="actor" label="处理人（手工记录）" rules={[{ required: true, whitespace: true, message: '请填写处理人' }]}>
            <Input placeholder="填写实际核对人员姓名" />
          </Form.Item>
          <Form.Item name="note" label="处理说明 / 依据" rules={[{ required: true, whitespace: true, message: '请记录本次处理依据' }]}>
            <Input.TextArea rows={4} placeholder="说明哪些配置适用、资料哪里有误，或还需要向谁确认" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={save.isPending}>保存处理结论</Button>
        </Form>
      </> },
      { key: 'history', label: `处理历史（${issue.history.length}）`, children: <History issue={issue} /> },
    ]} />
  </Drawer>;
}
