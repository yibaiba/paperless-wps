import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Collapse, Descriptions, Empty, Space, Spin, Tag, Typography } from 'antd';
import { api } from '../../../shared/api';
import type { Checked, Configuration, DeviceUsage, IssueAction } from '../types';
import { Status, useAttributeDefinitions } from '../shared';
import { configurationKeys } from '../queryKeys';
import { deviceChecks, usageDetails } from './usageDetails';
import { checkLabels } from './checkLabels';
import { EvidenceDetails } from '../EvidenceDetails';

interface Props {
  deviceId: string;
  configuration: Configuration;
  checked?: Checked;
  draftId?: string;
  draftRevision?: number;
  stale: boolean;
  onAction: (action: IssueAction) => void;
  onRecheck: () => void;
}

interface UsagePage { items: DeviceUsage[]; total: number }

export function DeviceUsagePanel({ deviceId, configuration, checked, draftId, draftRevision, stale, onAction, onRecheck }: Props) {
  const attributes = useAttributeDefinitions();
  const summaryUsage = checked?.device_usages.find(u => u.device_id === deviceId);
  const needsTrace = Boolean(summaryUsage && !summaryUsage.allocation_groups && draftId && draftRevision);
  const trace = useQuery({
    queryKey: configurationKeys.draftDeviceUsage(draftId, draftRevision, deviceId),
    enabled: needsTrace && !stale,
    queryFn: () => api<UsagePage>(`/work-drafts/${draftId}/device-usages?${new URLSearchParams({
      revision: String(draftRevision), device_id: deviceId, offset: '0', limit: '1',
    })}`),
  });
  if (configuration.calculation_version !== 3) return <Alert type="info" showIcon title="历史计算版本未记录用途明细"
    description="原计算结果保持不变；可在更多操作中预览并明确采用计算升级，再查看新版用途与分配。" />;
  const resourceName = (key?: string) => attributes.data?.find(a => a.key === key)?.label ?? key ?? '资源范围';
  const usage = trace.data?.items[0] ?? summaryUsage;
  const summary = usage?.quantity_summary;
  const supply = checked?.project_output.lines.find(l => l.device_id === deviceId)?.supply;
  if (!usage || !summary || stale) return <Alert type="warning" showIcon title="用途与分配待重新检查"
    description="保留已保存结果；预览后采用新的分配与检查明细，不改变产品或知识版本。"
    action={<Button onClick={onRecheck}>预览重新检查</Button>} />;
  if (trace.isLoading) return <Spin tip="读取设备用途追溯明细…"><div style={{ minHeight: 120 }} /></Spin>;
  if (trace.error) return <Alert type="error" showIcon title="用途追溯明细读取失败"
    description={trace.error.message} action={<Button onClick={() => trace.refetch()}>重试读取</Button>} />;
  const groups = usageDetails(usage, configuration);
  const issues = deviceChecks(checked!.checks, deviceId).filter(c => c.status !== 'pass');
  return <Space orientation="vertical" style={{ width: '100%' }}>
    {attributes.error ? <Alert type="error" title="资源名称读取失败" description={attributes.error.message} /> : null}
    <Descriptions size="small" bordered column={2} items={[
      { key: 'total', label: '部署总量', children: summary.total_quantity },
      { key: 'independent', label: '独立分配量', children: summary.independent_quantity },
      { key: 'shared', label: '共用实例占量', children: summary.shared_quantity },
      { key: 'unassigned', label: '未分配量', children: summary.unassigned_quantity },
      { key: 'extra', label: '超出数量', children: summary.overallocated_quantity },
    ]} />
    {supply ? <Descriptions size="small" column={2} title="供货分配" items={[
      { key: 'purchase', label: '本次采购', children: supply.purchase },
      { key: 'existing', label: '客户已有', children: supply.existing },
      { key: 'unknown', label: '供货待确认', children: supply.unknown },
      { key: 'unassigned', label: '尚未分配供货', children: supply.unassigned },
    ]} /> : null}
    {!groups.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未分配用途" /> : groups.map(group => <Card key={group.id} size="small"
      title={<Space><Tag>{group.label}</Tag><Typography.Text>实际占量 {group.quantity}</Typography.Text></Space>}>
      <Space orientation="vertical" size="small">
        {group.consumers.map(c => <Typography.Text key={c.id}>{c.label}</Typography.Text>)}
        {group.demand_ids.map(id => {
          const demand = checked!.suggestions.find(d => d.id === id);
          return <div key={id}><Typography.Text>配套：{demand?.need_name ?? id}</Typography.Text>
            {demand ? <Typography.Paragraph type="secondary">依据：{demand.rule.name} · 修订 {demand.rule.revision} · {demand.rule.evidence || '依据待确认'}</Typography.Paragraph> : null}</div>;
        })}
        {group.role_references.map(reference => <Alert key={reference.requirement_id} type="info" showIcon
          title="引用已有分配，不重复计量"
          description={`${configuration.requirements.find(r => r.id === reference.requirement_id)?.role ?? reference.requirement_id}：引用 ${reference.quantity}；覆盖 ${reference.group_ids.length} 个分配组`} />)}
      </Space>
    </Card>)}
    <Typography.Text strong>容量与承担范围</Typography.Text>
    {!usage.resource_calculations?.length ? <Typography.Text type="secondary">没有可用的资源计算明细，适用范围与资料缺口见下方检查。</Typography.Text> : usage.resource_calculations.map((check, index) => <Card key={`${check.allocation_group_id ?? check.code}:${check.resource}:${index}`} size="small">
      <Space><Status value={check.status} /><Typography.Text>{resourceName(check.resource)}</Typography.Text></Space>
      <Typography.Paragraph>需要 {check.required ?? '待明确分摊'} {check.unit}；可用 {check.capacity ?? '资料不足'} {check.unit}</Typography.Paragraph>
      <Typography.Paragraph type="secondary">{check.capacity_basis === 'unit' ? `单台容量 × 实际分配 ${check.allocated_quantity ?? '待确认'}` : check.capacity_basis === 'deployment' ? '部署容量口径' : check.message}</Typography.Paragraph>
      {check.allocation_group_id ? <Typography.Text type="secondary">承担用途：{groups.find(g => g.id === check.allocation_group_id)?.consumers.map(c => c.label).join('；')}</Typography.Text> : null}
      {check.evidence?.length ? <Collapse size="small" items={[{ key: 'evidence', label: '查看计算与原文依据', children: check.evidence.map((e, i) => <EvidenceDetails key={i} evidence={e} />) }]} /> : null}
    </Card>)}
    {usage.included_satisfactions?.length ? <Typography.Text type="secondary">已含内容单独满足 {usage.included_satisfactions.length} 项关联，不增加部署或采购数量。</Typography.Text> : null}
    {issues.map((issue, index) => <Alert key={issue.check_id ?? index} showIcon type={issue.status === 'conflict' ? 'error' : 'warning'}
      title={issue.message ?? (issue.resource ? `${resourceName(issue.resource)}：需求 ${issue.required ?? '待确认'}，容量 ${issue.capacity ?? '待确认'}` : `${checkLabels[issue.kind] ?? issue.kind}：依据待核对`)}
      description={issue.evidence?.length ? <Collapse size="small" items={[{ key: 'evidence', label: '查看条件与依据', children: issue.evidence.map((e, i) => <EvidenceDetails key={i} evidence={e} />) }]} /> : null}
      action={issue.action ? <Button size="small" onClick={() => onAction(issue.action!)}>处理</Button> : null} />)}
  </Space>;
}
