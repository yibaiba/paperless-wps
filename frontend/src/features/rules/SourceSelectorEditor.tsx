import {useMutation} from '@tanstack/react-query';
import {Alert,Button,Form,Select,Space,Table,Typography} from 'antd';
import type {FormInstance} from 'antd';
import {api} from '../../shared/api';
import type {Product} from '../../shared/types';
import {attributeLabels} from '../catalog/attributes/types';
import type {AttributeKey,SourceSelector} from '../catalog/attributes/types';
import {productLabel} from './types';
import type {RuleProduct} from './types';

export function selectorLabel(selector:SourceSelector) {
  return selector.conditions.map(c=>`${attributeLabels[c.field]}${c.operator==='all'?'包含全部':'包含任一'}「${c.values.join('、')}」`).join('，并且');
}

export function SourceSelectorEditor({form,products}:{form:FormInstance;products:Product[]}) {
  const selector=Form.useWatch('source_selector',form) as SourceSelector|undefined;
  const preview=useMutation({mutationFn:(value:SourceSelector)=>api<{products:RuleProduct[]}>('/rules/source-preview',{
    method:'POST',body:JSON.stringify(value),
  })});
  const current=preview.variables && JSON.stringify(preview.variables)===JSON.stringify(selector);
  return <>
    <Alert className="section-bottom" type="info" title="每一行条件都要满足；属性值按完整文本精确匹配。"
      description="仅匹配所选产品库版本内人工维护的属性，未填写不会猜测。属性修改后重新计算会自动更新适用产品；原项目来源快照和已应用记录保留。"/>
    <Form.Item name={['source_selector','import_id']} hidden><Select/></Form.Item>
    <Form.List name={['source_selector','conditions']} rules={[{validator:async(_,value)=>{
      if(!value?.length) throw new Error('至少填写一条属性条件');
    }}]}>
      {(fields,{add,remove},{errors})=><>
        {fields.map(field=>{
          const attribute = selector?.conditions?.[field.name]?.field ?? 'series';
          const options=[...new Set(products.flatMap(p=>p.attribute_profile.values[attribute]))].sort().map(value=>({value,label:value}));
          return <Space key={field.key} align="start" wrap>
            <Form.Item name={[field.name,'field']} label="条件属性" rules={[{required:true}]}><Select style={{width:140}}
              options={Object.entries(attributeLabels).map(([value,label])=>({value,label}))}/></Form.Item>
            <Form.Item name={[field.name,'operator']} label="匹配方式" rules={[{required:true}]}><Select style={{width:140}}
              options={[{value:'all',label:'包含全部值'},{value:'any',label:'包含任一值'}]}/></Form.Item>
            <Form.Item name={[field.name,'values']} label="条件值" rules={[{required:true,type:'array',min:1}]}><Select style={{minWidth:200,maxWidth:'100%'}} mode="tags" options={options}/></Form.Item>
            <Button aria-label={`移除条件 ${field.name+1}`} onClick={()=>remove(field.name)}>移除</Button>
          </Space>;
        })}
        <Form.ErrorList errors={errors}/>
        <Button className="section-bottom" onClick={()=>add({field:'series' as AttributeKey,operator:'all',values:[]})}>增加属性条件</Button>
      </>}
    </Form.List>
    <Form.Item name={['source_selector','exclude_product_ids']} label="例外：排除这些具体配置">
      <Select mode="multiple" showSearch optionFilterProp="label" options={products.map(p=>({value:p.id,label:productLabel(p)}))}/>
    </Form.Item>
    <Button className="section-bottom" loading={preview.isPending} onClick={()=>selector && preview.mutate(selector)}>预览匹配产品</Button>
    {preview.error ? <Alert type="error" title={preview.error.message}/>:null}
    {preview.data && current ? <>
      <Typography.Paragraph>当前匹配 {preview.data.products.length} 条来源记录。请核对配置和单位；零匹配时规则不会触发。</Typography.Paragraph>
      <Table<RuleProduct> size="small" rowKey="id" dataSource={preview.data.products} pagination={{pageSize:5,showSizeChanger:false}}
        columns={[{title:'匹配来源',key:'product',render:(_,p)=>productLabel(p)},{title:'单位',dataIndex:'unit',width:60}]}/>
    </>:null}
  </>;
}
