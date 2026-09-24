import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Alert,Button,Card,Empty,Modal,Space,Table,Tag,Typography} from 'antd';
import {selectorLabel} from './SourceSelectorEditor';
import {api} from '../../shared/api';
import {PageHeader} from '../../shared/PageHeader';
import {modeLabels,relationLabels,statusLabels} from './types';
import type {AccessoryRule} from './types';
import {Link} from 'react-router-dom';

function RuleHistory({rule,onClose}:{rule:AccessoryRule;onClose:()=>void}){
  const history=useQuery({queryKey:['rule-history',rule.id],queryFn:()=>api<(AccessoryRule&{created_at:string})[]>(`/rules/${rule.id}/history`)});
  return <Modal title={`旧规则历史 · ${rule.name}`} open onCancel={onClose} footer={<Button onClick={onClose}>关闭</Button>} width={760}>
    {history.error?<Alert type="error" title={history.error.message} showIcon/>:<Table rowKey="revision" loading={history.isLoading} dataSource={history.data} pagination={false} columns={[
      {title:'版本',dataIndex:'revision',width:80,render:value=>`v${value}`},
      {title:'数量规则',key:'rule',render:(_,item)=>`${modeLabels[item.mode]} · ${item.factor}`},
      {title:'状态',dataIndex:'status',width:90,render:value=><Tag>{statusLabels[value as AccessoryRule['status']]}</Tag>},
      {title:'维护依据',dataIndex:'evidence'},
      {title:'记录时间',dataIndex:'created_at',width:180,render:value=>new Date(value).toLocaleString('zh-CN')},
    ]}/>}
  </Modal>;
}

export default function RulesPage(){
  const [historyRule,setHistoryRule] = useState<AccessoryRule>();
  const rules = useQuery({queryKey:['rules'],queryFn:()=>api<AccessoryRule[]>('/rules')});
  return <>
    <PageHeader title="旧配套规则" description="保留迁移前的规则和版本历史。" actions={<Link to="/knowledge"><Button type="primary">前往搭配知识</Button></Link>}/>
    <Alert className="section-bottom" type="info" showIcon title="此处只读，不再建立或修改规则。"
      description={<>统一从<Link to="/knowledge">搭配知识</Link>维护配套需求、候选型号、计算范围和数量依据；原规则与历史继续保留。</>}/>
    {rules.error?<Alert type="error" title={rules.error.message} className="section-bottom"/>:null}
    <Card><Table<AccessoryRule> rowKey="id" loading={rules.isLoading} dataSource={rules.data} scroll={{x:1050}}
      locale={{emptyText:<Empty description="没有保留的旧配套规则"/>}} columns={[
        {title:'规则',key:'name',width:230,render:(_,r)=><Space orientation="vertical" size={4}><Typography.Text strong>{r.name}</Typography.Text>{r.matching_errors?.length?<Tag color="red">匹配条件需修正</Tag>:null}<Typography.Text type="secondary">v{r.revision} · {r.actor}</Typography.Text></Space>},
        {title:'触发 → 配套',key:'products',width:300,render:(_,r)=><Space orientation="vertical" size={3}><span>{r.source_selector?`${selectorLabel(r.source_selector)}（当前 ${r.sources.length} 条）`:r.sources.map(p=>p.model).join(' + ')} → {r.targets.map(p=>p.model).join(' / ')}</span><Typography.Text type="secondary">{r.source_selector?'按所选版本的产品属性匹配':r.source?`${r.source.sheet} 第${r.source.row}行`:'暂无匹配产品'} → {r.target.sheet} 第{r.target.row}行</Typography.Text></Space>},
        {title:'数量规则',key:'mode',render:(_,r)=><span>{relationLabels[r.relation]} · {modeLabels[r.mode]} · {r.factor}</span>},
        {title:'状态',dataIndex:'status',width:85,render:(value:AccessoryRule['status'])=><Tag color={value==='active'?'green':undefined}>{statusLabels[value]}</Tag>},
        {title:'操作',key:'action',width:110,render:(_,r)=><Button onClick={()=>setHistoryRule(r)}>查看历史</Button>},
      ]}/></Card>
    {historyRule?<RuleHistory rule={historyRule} onClose={()=>setHistoryRule(undefined)}/>:null}
  </>;
}
