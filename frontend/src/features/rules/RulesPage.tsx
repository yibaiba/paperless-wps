import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Alert,Button,Card,Empty,Space,Table,Tag,Typography} from 'antd';
import PlusOutlined from '@ant-design/icons/PlusOutlined';
import {selectorLabel} from './SourceSelectorEditor';
import {api} from '../../shared/api';
import {PageHeader} from '../../shared/PageHeader';
import {RuleDrawer} from './RuleDrawer';
import {modeLabels,relationLabels,statusLabels} from './types';
import type {AccessoryRule} from './types';

export default function RulesPage(){
  const [editing,setEditing] = useState<AccessoryRule>();
  const [creating,setCreating] = useState(false);
  const rules = useQuery({queryKey:['rules'],queryFn:()=>api<AccessoryRule[]>('/rules')});
  return <>
    <PageHeader title="配套规则" description="把已明确的配套关系变成可维护、可试算的数量规则。" actions={<Button type="primary" icon={<PlusOutlined/>} onClick={()=>setCreating(true)}>新建规则</Button>}/>
    <Alert className="section-bottom" type="info" showIcon title="GoRules ZEN 已接入，只有启用的规则参与项目计算。"
      description="支持按产品属性匹配、多个型号合计容量、必须配套及候选选择检查。规则以区域 / 系统分组；共享条件由维护人确认，原文备注不会自动变成规则。"/>
    {rules.error?<Alert type="error" title={rules.error.message} className="section-bottom"/>:null}
    <Card><Table<AccessoryRule> rowKey="id" loading={rules.isLoading} dataSource={rules.data} scroll={{x:1050}}
      locale={{emptyText:<Empty description="还没有配套规则，请选择真实产品并录入已确认的配套关系"/>}} columns={[
        {title:'规则',key:'name',width:230,render:(_,r)=><Space orientation="vertical" size={4}><Typography.Text strong>{r.name}</Typography.Text>{r.matching_errors?.length?<Tag color="red">匹配条件需修正</Tag>:null}<Typography.Text type="secondary">v{r.revision} · {r.actor}</Typography.Text></Space>},
        {title:'触发 → 配套',key:'products',width:300,render:(_,r)=><Space orientation="vertical" size={3}><span>{r.source_selector?`${selectorLabel(r.source_selector)}（当前 ${r.sources.length} 条）`:r.sources.map(p=>p.model).join(' + ')} → {r.targets.map(p=>p.model).join(' / ')}</span><Typography.Text type="secondary">{r.source_selector?'按所选版本的产品属性匹配':r.source?`${r.source.sheet} 第${r.source.row}行`:'暂无匹配产品'} → {r.target.sheet} 第{r.target.row}行</Typography.Text></Space>},
        {title:'数量规则',key:'mode',render:(_,r)=><span>{relationLabels[r.relation]} · {modeLabels[r.mode]} · {r.factor}</span>},
        {title:'状态',dataIndex:'status',width:85,render:(value:AccessoryRule['status'])=><Tag color={value==='active'?'green':undefined}>{statusLabels[value]}</Tag>},
        {title:'操作',key:'action',width:140,render:(_,r)=><Button onClick={()=>setEditing(r)}>编辑与试算</Button>},
      ]}/></Card>
    {creating||editing?<RuleDrawer key={editing?.id??'new'} rule={editing} onClose={()=>{setCreating(false);setEditing(undefined);}}/>:null}
  </>;
}
