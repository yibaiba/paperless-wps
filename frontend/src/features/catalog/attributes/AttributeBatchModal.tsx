import {useMutation,useQueryClient} from '@tanstack/react-query';
import {Alert,App,Form,Input,Modal,Select,Typography} from 'antd';
import {api} from '../../../shared/api';
import type {Product} from '../../../shared/types';
import {attributeLabels,attributeQueryKeys} from './types';
import type {AttributeKey} from './types';

interface Values {field:AttributeKey;values:string[];operation:'add'|'remove';actor:string;evidence:string}
export function AttributeBatchModal({products,onClose}:{products:Product[];onClose:()=>void}) {
  const [form]=Form.useForm<Values>();
  const client=useQueryClient();
  const {message}=App.useApp();
  const save=useMutation({mutationFn:(values:Values)=>api('/attributes/batch',{
    method:'POST',body:JSON.stringify({...values,items:products.map(p=>({product_id:p.id,expected_revision:p.attribute_profile.revision}))}),
  }),onSuccess:async()=>{
    await Promise.all(attributeQueryKeys.map(key=>client.invalidateQueries({queryKey:[key]})));
    message.success(`已维护 ${products.length} 条产品属性`);onClose();
  }});
  return <Modal title={`批量维护属性 · ${products.length} 条来源记录`} open onCancel={onClose}
    onOk={()=>form.submit()} okText="保存属性" cancelText="取消" confirmLoading={save.isPending}>
    <Alert type="info" title="只增补或移除指定属性值，其余属性和原文保留。" className="section-bottom"/>
    <Typography.Paragraph ellipsis={{rows:3,expandable:true}}>{products.map(p=>`${p.model}（${p.sheet} 第${p.row}行）`).join('、')}</Typography.Paragraph>
    {save.error?<Alert type="error" title={save.error.message}/>:null}
    <Form form={form} layout="vertical" initialValues={{operation:'add',field:'series'}} onFinish={values=>save.mutate(values)}>
      <Form.Item name="field" label="属性类别" rules={[{required:true}]}><Select options={Object.entries(attributeLabels).map(([value,label])=>({value,label}))}/></Form.Item>
      <Form.Item name="operation" label="维护方式" rules={[{required:true}]}><Select options={[{value:'add',label:'增补属性值'},{value:'remove',label:'移除指定属性值'}]}/></Form.Item>
      <Form.Item name="values" label="属性值" rules={[{required:true,type:'array',min:1}]}><Select mode="tags" tokenSeparators={['，',',']}/></Form.Item>
      <Form.Item name="evidence" label="属性依据" rules={[{required:true,whitespace:true}]}><Input.TextArea/></Form.Item>
      <Form.Item name="actor" label="属性维护人" rules={[{required:true,whitespace:true}]}><Input/></Form.Item>
    </Form>
  </Modal>;
}
