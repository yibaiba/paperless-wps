import {useState} from 'react';
import type {Key} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {Alert,App,Button,Card,Collapse,Drawer,Empty,Space,Table,Tabs,Tag,Typography} from 'antd';
import {selectorLabel} from './SourceSelectorEditor';
import {ConfigurationChecks} from './ConfigurationChecks';
import {api} from '../../shared/api';
import type {RuleApplication,RulePreview,Suggestion} from './types';

function Evidence({suggestion}: {suggestion:Suggestion}){
  return <Space orientation="vertical" style={{width:'100%'}}>{suggestion.rules.map(rule=><Card key={rule.rule_id} size="small" title={`${rule.name} · v${rule.revision}`}>
    <Typography.Paragraph>触发 {(rule.sources??(rule.source?[rule.source]:[])).map(p=>p.model).join(' + ')}，合计 {rule.input.quantity}，规则比例：{rule.input.factor}，配套需求：{rule.quantity}。</Typography.Paragraph>
    {rule.contributions?.map(item=><Typography.Text key={item.product_id} type="secondary">{rule.sources?.find(p=>p.id===item.product_id)?.model}：{item.quantity}； </Typography.Text>)}
    {rule.source_selector?<Typography.Paragraph>匹配条件：{selectorLabel(rule.source_selector)}。属性版本：{Object.entries(rule.attribute_snapshot??{}).map(([id,p])=>`${rule.sources?.find(s=>s.id===id)?.model??id} v${p.revision}`).join('、')}</Typography.Paragraph>:null}
    <Typography.Paragraph className="source-text">{rule.evidence}</Typography.Paragraph>
  </Card>)}</Space>;
}

function ApplicationHistory({projectId}:{projectId:string}){
  const history=useQuery({queryKey:['rule-applications',projectId],queryFn:()=>api<RuleApplication[]>(`/projects/${projectId}/rule-history`)});
  return <>
    {history.error?<Alert type="error" title={history.error.message}/>:null}
    <Table<RuleApplication> rowKey="id" dataSource={history.data} loading={history.isLoading}
      locale={{emptyText:<Empty description="尚未应用配套计算"/>}} columns={[
        {title:'应用时间',dataIndex:'created_at',render:value=>new Date(value).toLocaleString('zh-CN')},
        {title:'补入行数',key:'count',render:(_,entry)=>entry.item_ids.length},
      ]} expandable={{expandedRowRender:entry=><Space orientation="vertical" style={{width:'100%'}}>
        <Typography.Text type="secondary">此处保留应用当时的计算依据；之后手工调整清单不会改写这份记录。</Typography.Text>
        {entry.calculation.suggestions.map(s=><Card size="small" key={s.id} title={`${s.group_name} · ${s.target.model}`}>
          <Typography.Paragraph>需求 {s.required}，原有 {s.existing}，本次补入 {s.missing} {s.target.unit}。</Typography.Paragraph><Evidence suggestion={s}/>
        </Card>)}
      </Space>}}/>
  </>;
}

export function ProjectRulesDrawer({projectId,onClose}:{projectId:string;onClose:()=>void}){
  const [selected,setSelected]=useState<Key[]>([]);
  const client=useQueryClient();
  const {message}=App.useApp();
  const preview=useQuery({queryKey:['rule-preview',projectId],staleTime:0,queryFn:()=>api<RulePreview>(`/projects/${projectId}/rule-preview`)});
  const apply=useMutation({
    mutationFn:()=>api(`/projects/${projectId}/rule-apply`,{method:'POST',body:JSON.stringify({fingerprint:preview.data?.fingerprint,suggestion_ids:selected})}),
    onSuccess:async()=>{
      setSelected([]);
      await Promise.all(['project','projects','rule-preview','rule-applications'].map(key=>client.invalidateQueries({queryKey:[key]})));
      message.success('已按缺少数量补入清单，原有清单行保留');
    },
  });
  const error=preview.error||apply.error;
  return <Drawer title="清单检查与配套计算" open onClose={onClose} size={1060}>
    <Tabs items={[
      {key:'calculate',label:'计算与补足',children:<>
        <Alert className="section-bottom" type="info" showIcon title="共享型号必须放进同一规则；不同系统分别计算。"
          description="数量规则的需求相加；系统最低数量取最大值，并与数量需求取较大值。只抵扣同组同来源配置。检查基于已录入规则，不代表整套方案已通过。新增配套需重新计算下一层；超量不会自动删除。"/>
        {error?<Alert className="section-bottom" type="error" title={error.message}/>:null}
        <Space wrap className="section-bottom">
          <Button loading={preview.isFetching} onClick={()=>{setSelected([]);apply.reset();void preview.refetch();}}>重新计算</Button>
          <Button type="primary" loading={apply.isPending} disabled={!selected.length||preview.isFetching||Boolean(preview.error)} onClick={()=>apply.mutate()}>将所选缺量补入清单</Button>
          <Typography.Text type="secondary">{preview.data?.engine} · 启用规则 {preview.data?.active_rule_count??0} 条</Typography.Text>
        </Space>
        <ConfigurationChecks preview={preview.data}/>
        <Table<Suggestion> rowKey="id" dataSource={preview.data?.suggestions} loading={preview.isLoading} scroll={{x:850}} pagination={false}
          rowSelection={{selectedRowKeys:selected,onChange:setSelected,getCheckboxProps:r=>({disabled:Number(r.missing)<=0})}}
          locale={{emptyText:<Empty description="当前清单没有命中启用规则，请先配置并启用明确的配套关系"/>}}
          columns={[
            {title:'区域 / 系统',dataIndex:'group_name',width:160},
            {title:'配套产品',key:'target',width:250,render:(_,r)=><Space orientation="vertical" size={2}><Typography.Text strong>{r.target.model}</Typography.Text><span>{r.target.name}</span><Typography.Text type="secondary">{r.target.sheet} 第{r.target.row}行</Typography.Text></Space>},
            {title:'检查',key:'check',width:130,render:(_,r)=><Tag color={Number(r.missing)>0?'orange':'green'}>{Number(r.missing)>0?(r.mandatory?'缺少必配':'数量不足'):'数量已满足'}</Tag>},
            {title:'需求',dataIndex:'required',width:85},{title:'已有',dataIndex:'existing',width:85},
            {title:'应补',dataIndex:'missing',width:85,render:value=><Typography.Text strong>{value}</Typography.Text>},
            {title:'超出',dataIndex:'surplus',width:85},{title:'单位',key:'unit',render:(_,r)=>r.target.unit},
          ]} expandable={{expandedRowRender:r=><Evidence suggestion={r}/>}}/>
        <Collapse className="section-gap" items={[{key:'uncovered',label:`未触发规则的清单行（${preview.data?.uncovered_items.length??0}）`,children:<>
          <Typography.Paragraph type="secondary">这些行可能无需配套，也可能尚未配置规则，不能据此认定清单完整。</Typography.Paragraph>
          {preview.data?.uncovered_items.map(item=><Typography.Paragraph key={item.id}>{item.group_name} · {item.model} · {item.quantity}</Typography.Paragraph>)}
        </>}]}/>
      </>},
      {key:'history',label:'应用记录',children:<ApplicationHistory projectId={projectId}/>},
    ]}/>
  </Drawer>;
}
