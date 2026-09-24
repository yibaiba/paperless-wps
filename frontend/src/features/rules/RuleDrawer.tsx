import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Drawer, Form, Input, InputNumber, Select, Space, Tabs, Timeline, Typography } from 'antd';
import {SourceSelectorEditor,selectorLabel} from './SourceSelectorEditor';
import { api } from '../../shared/api';
import type { CatalogImport, Product } from '../../shared/types';
import { modeLabels, productLabel, relationLabels, statusLabels } from './types';
import type { AccessoryRule, Calculation } from './types';

type RuleValues = Pick<AccessoryRule, 'source_selector' | 'additional_source_ids' | 'alternative_target_ids' | 'relation' | 'name' | 'source_product_id' | 'target_product_id' | 'mode' | 'factor' | 'status' | 'evidence' | 'actor'>;

function RuleTrial({rule}: {rule: AccessoryRule}) {
  const [quantity, setQuantity] = useState<string | null>('21');
  const trial = useMutation({mutationFn: () => api<Calculation>(`/rules/${rule.id}/trial`, {
    method: 'POST', body: JSON.stringify({quantity}),
  })});
  return <Space orientation="vertical" size={20} style={{width:'100%'}}>
    <Alert type="info" title={`试算使用已保存的 v${rule.revision} 规则`} description={`${rule.sources.map(p=>p.model).join(' + ')} → ${rule.target.model}；${modeLabels[rule.mode]}，比例 ${rule.factor}。编辑后请先保存。`} />
    <Space wrap><Typography.Text>触发产品合计数量</Typography.Text><InputNumber aria-label="试算触发数量" stringMode min="0" value={quantity} onChange={setQuantity} /><Button onClick={() => trial.mutate()} loading={trial.isPending}>运行试算</Button></Space>
    {trial.error ? <Alert type="error" title={trial.error.message} /> : null}
    {trial.data ? <Alert type="success" title={rule.relation==='choice'?`候选合计需要 ${trial.data.quantity} ${rule.target.unit}，具体型号需人工选择`:`需要 ${trial.data.quantity} ${rule.target.unit} ${rule.target.model}`}
      description={`实际输入 ${trial.data.input.quantity}，比例 ${trial.data.input.factor}。由 ${trial.data.engine} 执行；试算不修改项目，也不检查现有配套或兼容性。`} /> : null}
    <Typography.Paragraph className="source-text">依据：{rule.evidence}</Typography.Paragraph>
  </Space>;
}

function RuleHistory({rule}: {rule: AccessoryRule}) {
  const history = useQuery({queryKey:['rule-history',rule.id], queryFn:() => api<(AccessoryRule & {created_at:string})[]>(`/rules/${rule.id}/history`)});
  return <>
    {history.error ? <Alert type="error" title={history.error.message} /> : null}
    <Timeline items={history.data?.map(item => ({key:item.revision, content:<>
      <Typography.Text strong>v{item.revision} · {statusLabels[item.status]} · {item.actor}</Typography.Text>
      <Typography.Paragraph type="secondary">{new Date(item.created_at).toLocaleString('zh-CN')}</Typography.Paragraph>
      {item.source_selector?<Typography.Paragraph>保存时条件：{selectorLabel(item.source_selector)}；以下为当时匹配的来源。</Typography.Paragraph>:null}
      <Typography.Paragraph>{item.sources.map(productLabel).join(' + ')} → {item.targets.map(productLabel).join(' / ')}</Typography.Paragraph>
      <Typography.Paragraph>{relationLabels[item.relation]} · {modeLabels[item.mode]}，比例 {item.factor}</Typography.Paragraph>
      <Typography.Paragraph className="source-text">{item.evidence}</Typography.Paragraph>
    </>}))} />
  </>;
}

export function RuleDrawer({rule,onClose}: {rule?:AccessoryRule;onClose:()=>void}) {
  const [form] = Form.useForm<RuleValues>();
  const [version,setVersion] = useState(rule?.source_selector?.import_id ?? rule?.source?.import_id ?? rule?.target.import_id);
  const [matching,setMatching] = useState(rule?.source_selector?'attributes':'products');
  const [revision] = useState(rule?.revision);
  const mode = Form.useWatch('mode',form) ?? rule?.mode ?? 'per_capacity';
  const relation = Form.useWatch('relation',form) ?? rule?.relation ?? 'quantity';
  const client = useQueryClient();
  const {message} = App.useApp();
  const imports = useQuery({queryKey:['imports'],queryFn:()=>api<CatalogImport[]>('/imports')});
  const importId = version ?? imports.data?.[0]?.id;
  const products = useQuery({queryKey:['products',importId],enabled:Boolean(importId),queryFn:()=>api<Product[]>(`/products?import_id=${importId}`)});
  const options = products.data?.map(p=>({value:p.id,label:productLabel(p)}));
  const save = useMutation({
    mutationFn:(values:RuleValues)=>api<AccessoryRule>(`/rules${rule?`/${rule.id}`:''}`,{
      method:rule?'PUT':'POST',body:JSON.stringify({
        ...values, source_selector:matching==='attributes'?values.source_selector:null,
        source_product_id:matching==='attributes'?null:values.source_product_id,
        additional_source_ids:matching==='attributes'?[]:values.additional_source_ids,
        ...(rule?{expected_revision:revision}:{}),
      }),
    }),
    onSuccess:async()=>{
      await Promise.all(['rules','rule-history','rule-preview'].map(key=>client.invalidateQueries({queryKey:[key]})));
      message.success('规则已保存');onClose();
    },
  });
  return <Drawer title={rule?`编辑规则 · v${rule.revision}`:'新建配套规则'} open onClose={onClose} size={760}>
    <Tabs items={[
      {key:'edit',label:'规则配置',children:<>
        <Alert className="section-bottom" type="info" title="规则可按属性条件或具体型号匹配，按区域 / 系统分别计算。"
          description="匹配本条规则的产品会共同合计；区域 / 系统字段是共享边界。跨会议室共用时需使用同一系统标识。不同容量规则仍各自计算，不能代替共享规则。" />
        {rule?.matching_errors?.length?<Alert type="error" title={rule.matching_errors.join("；")} className="section-bottom"/>:null}
        {imports.error || products.error || save.error ? <Alert className="section-bottom" type="error" title={(imports.error||products.error||save.error)?.message} /> : null}
        <Form form={form} layout="vertical" initialValues={rule?{
          source_selector:rule.source_selector,additional_source_ids:rule.additional_source_ids,alternative_target_ids:rule.alternative_target_ids,relation:rule.relation,
          name:rule.name,source_product_id:rule.source_product_id,target_product_id:rule.target_product_id,
          mode:rule.mode,factor:rule.factor,status:rule.status,evidence:rule.evidence,actor:'',
        }:{additional_source_ids:[],alternative_target_ids:[],relation:'quantity',mode:'per_capacity',factor:'1',status:'draft'}} onFinish={values=>save.mutate(values)}>
          <Form.Item name="name" label="规则名称" rules={[{required:true,whitespace:true}]}><Input placeholder="例如：会议话筒配分线盒" /></Form.Item>
          <Form.Item label="选品来源版本"><Select aria-label="规则选品来源版本" value={importId} onChange={value=>{setVersion(value);if(matching==='attributes')form.setFieldValue('source_selector',{...form.getFieldValue('source_selector'),import_id:value,exclude_product_ids:[]});form.setFieldsValue({source_product_id:undefined,target_product_id:undefined,additional_source_ids:[],alternative_target_ids:[]});}} options={imports.data?.map(i=>({value:i.id,label:i.filename}))} /></Form.Item>
          <Form.Item name="relation" label="配套关系" rules={[{required:true}]}><Select onChange={()=>form.setFieldValue('alternative_target_ids',[])} options={Object.entries(relationLabels).map(([value,label])=>({value,label}))} /></Form.Item>
          <Form.Item label="触发范围"><Select aria-label="触发范围" value={matching} options={[{value:'products',label:'指定具体型号'},{value:'attributes',label:'按产品属性匹配'}]}
            onChange={value=>{setMatching(value);form.setFieldsValue({source_product_id:null,additional_source_ids:[],source_selector:value==='attributes'?{import_id:importId!,conditions:[{field:'series',operator:'all',values:[]}],exclude_product_ids:[]}:null});}}/></Form.Item>
          {matching==='attributes'?<SourceSelectorEditor form={form} products={products.data??[]}/>:<>
          <Form.Item name="source_product_id" label="触发产品" rules={[{required:true}]}><Select showSearch optionFilterProp="label" placeholder="选择主设备的具体配置" options={options} loading={products.isLoading} /></Form.Item>
          <Form.Item name="additional_source_ids" label="共同合计的其他型号" extra="只选择已确认可共同计量的配置；同一系统内先合计，再计算配套数量。"><Select mode="multiple" showSearch optionFilterProp="label" options={options} placeholder="没有共享型号可留空" /></Form.Item>
          </>}
          <Form.Item name="target_product_id" label="配套产品" rules={[{required:true}]}><Select showSearch optionFilterProp="label" placeholder="选择要补入的配件、授权或线材" options={options} loading={products.isLoading} /></Form.Item>
          {relation==='choice'?<Form.Item name="alternative_target_ids" label="其他可选配套" rules={[{required:true,type:'array',min:1}]} extra="首个配套和这里的候选合计已有数量；不足时提醒人工选型，不自动全部加入。候选角色、兼容条件仍需在依据中说明。"><Select mode="multiple" showSearch optionFilterProp="label" options={options} /></Form.Item>:null}
          <Form.Item name="mode" label="计算方式" rules={[{required:true}]}><Select options={Object.entries(modeLabels).map(([value,label])=>({value,label}))} /></Form.Item>
          <Form.Item name="factor" label={mode==='per_group'?'出现触发产品时，每个系统至少需要多少配套':mode==='per_capacity'?'每 1 件配套可承载多少触发产品':'每 1 件触发产品需要多少配套'} rules={[{required:true}]}><InputNumber stringMode style={{width:'100%'}} /></Form.Item>
          <Form.Item name="status" label="使用状态" rules={[{required:true}]}><Select options={Object.entries(statusLabels).map(([value,label])=>({value,label}))} /></Form.Item>
          <Form.Item name="evidence" label="来源依据与适用说明" rules={[{required:true,whitespace:true}]}><Input.TextArea rows={4} placeholder="写明资料位置、配套关系、适用范围及计量单位" /></Form.Item>
          <Form.Item name="actor" label="本次维护人（手工记录）" rules={[{required:true,whitespace:true}]}><Input /></Form.Item>
          <Button type="primary" htmlType="submit" loading={save.isPending}>保存规则</Button>
        </Form>
      </>},
      ...(rule?[{key:'trial',label:'数量试算',children:<RuleTrial rule={rule}/>},{key:'history',label:'版本历史',children:<RuleHistory rule={rule}/>}]:[]),
    ]}/>
  </Drawer>;
}
