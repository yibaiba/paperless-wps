import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {Alert, App, Button, Form, Input, Select, Timeline, Typography} from 'antd';
import {api} from '../../../shared/api';
import type {ProductDetail} from '../../../shared/types';
import {attributeLabels, attributeQueryKeys} from './types';
import type {AttributeProfile, AttributeValues} from './types';

export function AttributeEditor({product}:{product:ProductDetail}) {
  const client = useQueryClient();
  const {message} = App.useApp();
  const history = useQuery({queryKey:['attribute-history', product.id],
    queryFn:()=>api<AttributeProfile[]>(`/products/${product.id}/attributes/history`)});
  const save = useMutation({mutationFn:(values:{values:AttributeValues;actor:string;evidence:string})=>
    api(`/products/${product.id}/attributes`,{method:'PUT',body:JSON.stringify({
      ...values, expected_revision:product.attribute_profile.revision,
    })}),onSuccess:async()=>{
      await Promise.all(attributeQueryKeys.map(key=>client.invalidateQueries({queryKey:[key]})));
      message.success('属性已保存，属性规则会按新值匹配；已有应用记录保留');
    }});
  return <>
    <Alert className="section-bottom" type="info" title="这些属性用于规则匹配，独立于 Excel 原文。"
      description="填写明确的系列、功能、接口和系统；保存后会影响本来源版本的属性规则。相同含义请使用相同写法，不会自动合并近义词。"/>
    {save.error || history.error ? <Alert type="error" title={(save.error||history.error)?.message}/>:null}
    <Form layout="vertical" initialValues={{values:product.attribute_profile.values}} onFinish={values=>save.mutate(values)}>
      {Object.entries(attributeLabels).map(([key,label])=><Form.Item key={key} name={['values',key]} label={label}>
        <Select mode="tags" tokenSeparators={['，',',']} placeholder="输入属性值，按回车确认；可填写多个"/>
      </Form.Item>)}
      <Form.Item name="evidence" label="属性依据" rules={[{required:true,whitespace:true}]}><Input.TextArea rows={3} placeholder="来源工作表、单元格或已确认的产品说明"/></Form.Item>
      <Form.Item name="actor" label="属性维护人" rules={[{required:true,whitespace:true}]}><Input/></Form.Item>
      <Button type="primary" htmlType="submit" loading={save.isPending}>保存产品属性</Button>
    </Form>
    <Typography.Title level={5}>属性历史</Typography.Title>
    <Timeline items={history.data?.map(entry=>({key:entry.revision,content:<>
      <Typography.Text strong>v{entry.revision} · {entry.actor}</Typography.Text>
      <Typography.Paragraph>{entry.updated_at ? new Date(entry.updated_at).toLocaleString('zh-CN'):''}</Typography.Paragraph>
      {Object.entries(entry.values).map(([key,values])=><div key={key}>{attributeLabels[key as keyof AttributeValues]}：{values.join('、')||'未填写'}</div>)}
      <Typography.Paragraph>{entry.evidence}</Typography.Paragraph>
    </>}))}/>
  </>;
}
