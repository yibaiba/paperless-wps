import { KnowledgeGapList, type KnowledgeGap } from "./KnowledgeGapList";
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Collapse, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../../shared/api';
import { ROOT, Status } from '../shared';
import { configurationKeys } from '../queryKeys';
import type { Knowledge, KnowledgePackage } from '../types';

import { PackageTrial } from "./PackageTrial";
import { requiredRoleLabel } from "../projects/definitionSelection";

type Rule = {
  id: string; revision: number; name: string; kind: string; status: string;
  missing: string[]; evidence: string; condition_fields: string[]; quantity_key: string;
  evidence_refs: { source_id: string; locator: string; quote: string }[];
};
type Role = {
  id: string; name: string; required: boolean; feature: string; capability_ids: string[]; candidate_ids: string[]; rule_ids: string[]; missing: string[];
  coverage: { evidence: string }[];
};
type Report = {
  gaps: KnowledgeGap[];
  notice: string; roles: Role[]; rules: Rule[]; unmapped_rule_ids: string[];
  sharing_rule_ids: string[]; definition_status: "draft" | "confirmed";
  version_changes: { id: string; name: string; used: number; latest: number | null }[];
  summary: { roles: number; rules: number; confirmed_relations: number; roles_with_gaps: number; rules_with_gaps: number };
};

export function PackageReadiness({ bundle, knowledge, definitionRevision, onEdit }: {
  bundle: KnowledgePackage; knowledge: Knowledge[]; definitionRevision: number; onEdit: (rule: Knowledge) => void;
}) {
  const report = useQuery({
    queryKey: configurationKeys.packageReadiness({ id: bundle.id, revision: bundle.revision, knowledgeRevision: knowledge.filter(k => bundle.members.some(m => m.id === k.id)).map(k => `${k.id}:${k.revision}`).join('|'), definitionRevision }),
    queryFn: () => api<Report>(`${ROOT}/knowledge-packages/${bundle.id}/readiness`),
  });
  const data = report.data;
  return <Card size="small" title={`${bundle.name} · 可用范围检查`} loading={report.isPending} extra={<PackageTrial bundle={bundle} />}>
    {report.error ? <Alert type="error" title="可用范围读取失败" description={report.error.message} action={<Button onClick={() => report.refetch()}>重试</Button>} /> : null}
    {data ? <Space orientation="vertical" style={{ width: '100%' }}>
      <Alert showIcon type="info" title="这里显示知识准备情况，项目选型仍需逐项检查" description={data.notice} />
      <Space wrap><Tag>角色 {data.summary.roles} 个</Tag><Tag>关系已确认 {data.summary.confirmed_relations} / {data.summary.rules}</Tag><Tag color="orange">有待办的角色 {data.summary.roles_with_gaps} 个</Tag><Tag color="orange">有待办的关系 {data.summary.rules_with_gaps} 条</Tag></Space>
      {data.version_changes.length ? <Alert type="warning" title="引用资料已有新修订，本包仍使用原修订" description={data.version_changes.map(v => `${v.name}：引用 v${v.used} / 最新 ${v.latest ?? '不存在'}`).join('；')} /> : null}
      {data.unmapped_rule_ids.length ? <Alert type="warning" title={`${data.unmapped_rule_ids.length} 条适用关系尚未匹配本分支角色，原有确认不代表本分支兼容`} /> : null}
      {!data.sharing_rule_ids.length ? <Alert type="warning" title="包内没有已确认共享依据；选择共用设备时仍需核对" /> : null}
      <Table<Role> rowKey="id" size="small" pagination={false} dataSource={data.roles} scroll={{ x: 700 }} columns={[
        { title: '角色 / 何时需要', render: (_, r) => <>{r.name}<div><Typography.Text type="secondary">{requiredRoleLabel(r, data.definition_status)}</Typography.Text></div></>, width: 200 },
        { title: '已关联候选', render: (_, r) => `${r.candidate_ids.length} 个明确配置 / ${r.rule_ids.length} 条关系`, width: 220 },
        { title: '还需要补什么', render: (_, r) => r.missing.join('；') || '已登记覆盖结论，具体适配以项目检查为准' },
      ]} expandable={{ expandedRowRender: r => <Space orientation="vertical">{r.coverage.map((c, i) => <Typography.Paragraph key={i}>{c.evidence}</Typography.Paragraph>)}{r.rule_ids.map(id => { const rule = knowledge.find(k => k.id === id); return rule ? <Button key={id} onClick={() => onEdit(rule)}>维护：{rule.name}</Button> : null; })}</Space> }} />
      <Collapse items={[{ key: 'gaps', label: `可定位的资料缺口 · ${data.gaps.length} 项`, children: <KnowledgeGapList gaps={data.gaps} /> }, { key: 'rules', label: `配套、数量、条件及出处 · ${data.rules.length} 条`, children: <Table<Rule> rowKey="id" dataSource={data.rules} size="small" scroll={{ x: 850 }} columns={[
        { title: '固定修订', render: (_, r) => <>{r.name}<div>v{r.revision} · <Status value={r.status} /></div></> },
        { title: '待办', render: (_, r) => <>{r.missing.join('；') || '关系字段已登记，需按具体条件检查'}</> },
        { title: '项目需提供的字段', render: (_, r) => [...r.condition_fields, r.quantity_key].filter(Boolean).join('、') || '本关系未登记输入字段' },
        { title: '维护', render: (_, r) => { const current = knowledge.find(k => k.id === r.id); return <Button disabled={!current} onClick={() => current && onEdit(current)}>核对最新关系</Button>; } },
      ]} expandable={{ expandedRowRender: r => <><Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{r.evidence}</Typography.Paragraph>{r.evidence_refs.map((e, i) => <Typography.Paragraph key={i}>{e.locator}：{e.quote}</Typography.Paragraph>)}</> }} /> }]} />
    </Space> : null}
  </Card>;
}
