import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Col, Empty, Flex, Input, Row, Select, Statistic, Table, Tag, Typography } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { api } from '../../shared/api';
import { PageHeader } from '../../shared/PageHeader';
import { useCatalog } from '../../shared/useCatalog';
import type { Issue, ReviewStatus } from '../../shared/types';
import { IssueReviewDrawer } from './IssueReviewDrawer';
import { reviewColors, reviewLabels } from './reviewLabels';

const labels: Record<string, string> = {
  name_difference: '名称差异', configuration_difference: '参数 / 配置差异', missing_name: '字段待核对', note_difference: '配套 / 适用说明',
};

export default function IssuesPage() {
  const { imports, selectedId, select } = useCatalog();
  const [params, setParams] = useSearchParams();
  const [kind, setKind] = useState<string>();
  const [status, setStatus] = useState<ReviewStatus>();
  const [editingId, setEditingId] = useState<string>();
  const search = params.get('model') ?? '';
  const issues = useQuery({
    queryKey: ['issues', selectedId], enabled: Boolean(selectedId),
    queryFn: () => api<Issue[]>(`/issues?import_id=${selectedId}`),
  });
  const client = useQueryClient();
  const {message} = App.useApp();
  const recheck = useMutation({
    mutationFn: () => api<{added:number;total:number}>(`/imports/${selectedId}/recheck`, {method:'POST'}),
    onSuccess: async result => {
      await Promise.all(['imports','issues','products','product','project','rule-preview'].map(key=>client.invalidateQueries({queryKey:[key]})));
      message.success(`检查完成，新增 ${result.added} 项差异，原处理记录保留`);
    },
  });
  const records = issues.data ?? [];
  const pending = records.filter(i => i.review.status === 'pending').length;
  const sourceErrors = records.filter(i => i.review.status === 'source_error').length;
  const filtered = records.filter(i => (!kind || i.kind === kind) && (!status || i.review.status === status)
    && i.evidence.some(e => e.model.toLowerCase().includes(search.trim().toLowerCase())));
  const editing = records.find(i => i.id === editingId);
  const error = imports.error || issues.error || recheck.error;
  const updateSearch = (value: string) => setParams(previous => {
    const next = new URLSearchParams(previous);
    if (value) next.set('model', value); else next.delete('model');
    return next;
  }, { replace: true });

  return <>
    <PageHeader title="资料核对" description="对照来源、记录处理依据，让每项差异都有明确结论。" actions={<Button disabled={!selectedId} loading={recheck.isPending} onClick={()=>recheck.mutate()}>重新检查资料差异</Button>} />
    {error ? <Alert className="section-bottom" type="error" title={error.message} showIcon /> : null}
    <Row gutter={[16, 16]} className="section-bottom">
      <Col xs={24} sm={8}><Card loading={issues.isLoading || imports.isLoading}><Statistic title="待确认" value={pending} suffix="项" /></Card></Col>
      <Col xs={24} sm={8}><Card loading={issues.isLoading || imports.isLoading}><Statistic title="原资料有误待修订" value={sourceErrors} suffix="项" /></Card></Col>
      <Col xs={24} sm={8}><Card loading={issues.isLoading || imports.isLoading}><Statistic title="已确认配置或表述差异" value={records.length - pending - sourceErrors} suffix="项" /></Card></Col>
    </Row>
    <Alert className="section-bottom" type="info" showIcon title="当前检查覆盖名称、完整参数、配套备注差异和部分字段缺失。"
      description="处理结论会同步显示在选品和清单中；不会自动修改原文，也不代表兼容性、配套或停产状态已完成校验。" />
    <Card>
      <Flex wrap gap={12} align="center" className="section-bottom">
        <Select aria-label="核对产品库版本" className="version-select" value={selectedId}
          onChange={value => { select(value); setEditingId(undefined); }} placeholder="选择产品库版本"
          options={imports.data?.map(i => ({ value: i.id, label: i.filename }))} />
        <Input aria-label="搜索差异型号" className="sheet-select" placeholder="搜索产品型号" allowClear
          value={search} onChange={event => updateSearch(event.target.value)} />
        <Select aria-label="差异类型" className="sheet-select" placeholder="全部差异类型" allowClear value={kind} onChange={setKind}
          options={Object.entries(labels).map(([value, label]) => ({ value, label }))} />
        <Select aria-label="处理状态" className="sheet-select" placeholder="全部处理状态" allowClear value={status} onChange={setStatus}
          options={Object.entries(reviewLabels).map(([value, label]) => ({ value, label }))} />
        <Typography.Text type="secondary">当前 {filtered.length} / {records.length} 项</Typography.Text>
      </Flex>
      <Table<Issue> rowKey="id" loading={issues.isLoading || imports.isLoading} dataSource={filtered}
        pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ x: 1050 }}
        locale={{ emptyText: <Empty description={selectedId ? '当前筛选下没有差异记录' : '请先导入产品库'} /> }}
        columns={[
          { title: '类型', dataIndex: 'kind', width: 155, render: value => <Tag>{labels[value]}</Tag> },
          { title: '产品型号', key: 'model', width: 190, render: (_, issue) => <Typography.Text strong>{issue.evidence[0]?.model}</Typography.Text> },
          { title: '核对内容', dataIndex: 'description' },
          { title: '处理状态', key: 'status', width: 190, render: (_, issue) => <>
            <Tag color={reviewColors[issue.review.status]}>{reviewLabels[issue.review.status]}</Tag>
            {issue.review.actor ? <Typography.Paragraph type="secondary" className="review-actor">{issue.review.actor} · 第 {issue.review.revision} 次处理</Typography.Paragraph> : null}
          </> },
          { title: '操作', key: 'action', width: 135, render: (_, issue) => <Button onClick={() => setEditingId(issue.id)}>查看与处理</Button> },
        ]} />
    </Card>
    {editing ? <IssueReviewDrawer key={editing.id} issue={editing} onClose={() => setEditingId(undefined)} /> : null}
  </>;
}
