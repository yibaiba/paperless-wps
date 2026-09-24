import {Alert, Card, Collapse, Space, Tag, Typography} from 'antd';
import {Link} from 'react-router-dom';
import type {RulePreview} from './types';
import {productLabel} from './types';

export function ConfigurationChecks({preview}: {preview?:RulePreview}) {
  if (!preview) return null;
  const pending = preview.pending_relations ?? [];
  const concerns = preview.source_concerns ?? [];
  return <Space orientation="vertical" className="section-bottom" style={{width:'100%'}}>
    {pending.length ? <Alert type="warning" showIcon title={`${pending.length} 条相关规则仍为草稿，未参与计算`}
      description={<>{pending.map(r=><div key={r.id}>{r.name} · v{r.revision}</div>)}<Link to="/rules">到配套规则核对并维护</Link></>} /> : null}
    {concerns.length ? <Collapse style={{width:'100%'}} items={[{
      key:'sources', label:`${concerns.length} 项相关资料待核对，数量计算不代表配置已确认`,
      children:concerns.map(issue=><Typography.Paragraph key={issue.id}>
        <Link to={`/issues?import=${encodeURIComponent(issue.import_id)}&model=${encodeURIComponent(issue.evidence[0].model)}`}>
          {issue.evidence[0].model} · {issue.title}
        </Link>
      </Typography.Paragraph>),
    }]} /> : null}
    {(preview.choice_checks ?? []).map(check=><Card key={check.id} size="small" style={{width:'100%'}}
      title={<Space wrap><Tag color={check.status==='needs_selection'?'orange':'green'}>
        {check.status==='needs_selection'?'需要选择配套':'候选合计数量已满足'}</Tag>{check.group_name} · {check.rule.name}</Space>}>
      <Typography.Paragraph>需求 {check.required}，候选中已有 {check.existing}，还缺 {check.missing}。候选的角色与兼容性需按项目确认。</Typography.Paragraph>
      {check.targets.map(target=><Typography.Paragraph key={target.id}>{productLabel(target)}</Typography.Paragraph>)}
      <Typography.Paragraph className="source-text">依据：{check.rule.evidence}</Typography.Paragraph>
      {check.status==='needs_selection'?<Typography.Text type="secondary">关闭此面板后，在项目清单添加选定配置及数量，再重新计算；不会把全部候选自动加入。</Typography.Text>:null}
    </Card>)}
  </Space>;
}
