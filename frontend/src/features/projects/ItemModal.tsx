import { Alert, App, Form, Input, InputNumber, Modal, Select } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api';
import type { CatalogImport, Product, ProjectItem } from '../../shared/types';
import { useState } from 'react';
import { summaryText } from '../catalog/reviewLabels';
import { ReviewSummaryTag } from '../catalog/ReviewSummaryTag';

interface ItemValues { product_id: string; quantity: string; group_name: string; note: string }

export function ItemModal({ projectId, item, open, onClose }: {
  projectId: string; item?: ProjectItem; open: boolean; onClose: () => void;
}) {
  const [form] = Form.useForm<ItemValues>();
  const productId = Form.useWatch('product_id', form);
  const [version, setVersion] = useState<string>();
  const client = useQueryClient();
  const { message } = App.useApp();
  const imports = useQuery({ queryKey: ['imports'], queryFn: () => api<CatalogImport[]>('/imports') });
  const importId = version ?? imports.data?.[0]?.id;
  const products = useQuery({
    queryKey: ['products', importId], enabled: Boolean(importId),
    queryFn: () => api<Product[]>(`/products?import_id=${importId}`),
  });
  const save = useMutation({
    mutationFn: (values: ItemValues) => {
      const body = item ? { quantity: values.quantity, group_name: values.group_name, note: values.note ?? '' } : { ...values, note: values.note ?? '' };
      return api(`/projects/${projectId}/items${item ? `/${item.id}` : ''}`, { method: item ? 'PATCH' : 'POST', body: JSON.stringify(body) });
    },
    onSuccess: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: ['project', projectId] }), client.invalidateQueries({ queryKey: ['projects'] })]);
      message.success(item ? '清单行已更新' : '已添加到清单'); onClose();
    },
    onError: error => message.error(error.message),
  });
  const selected = products.data?.find(product => product.id === productId);
  const summary = item?.review_summary ?? selected?.review_summary;
  return <Modal title={item ? '编辑清单行' : '从产品库添加'} open={open} onCancel={onClose} onOk={() => form.submit()} confirmLoading={save.isPending} okText="保存" cancelText="取消" destroyOnHidden>
    <Form form={form} layout="vertical" onFinish={values => save.mutate(values)} initialValues={item ? { ...item } : { quantity: '1', group_name: '默认分组', note: '' }} preserve={false}>
      {!item ? <>
        <Form.Item label="产品库版本"><Select aria-label="添加产品的来源版本" value={importId} onChange={value => { setVersion(value); form.setFieldValue('product_id', undefined); }} options={imports.data?.map(i => ({ value: i.id, label: i.filename }))} /></Form.Item>
        <Form.Item label="具体来源产品" name="product_id" rules={[{ required: true, message: '请选择具体产品记录' }]}>
          <Select showSearch optionFilterProp="label" placeholder="搜索型号或产品名称" loading={products.isLoading} options={products.data?.map(p => ({ value: p.id, label: `${p.model} · ${p.name} · ${p.sheet} 第${p.row}行 · ${summaryText(p.review_summary)}` }))} />
        </Form.Item>
      </> : <p>{item.snapshot.model} · {item.snapshot.name}</p>}
      {summary ? <div className="section-bottom"><ReviewSummaryTag summary={summary} />
        {summary.pending || summary.source_error ? <Alert className="section-gap" type="warning" showIcon title="关联资料仍有待跟进事项" description="请结合来源依据选用；这里保留人工选品，不自动更换或合并配置。" /> : null}
      </div> : null}
      {imports.error || products.error ? <p role="alert">{(imports.error || products.error)?.message}</p> : null}
      <Form.Item label="所属区域 / 系统" name="group_name" rules={[{ required: true, whitespace: true, message: '请填写分组' }]}><Input placeholder="例如：一号会议室 / 音频系统" /></Form.Item>
      <Form.Item label="数量" name="quantity" rules={[{ required: true, message: '请填写数量' }, { validator: (_, value) => Number(value) > 0 ? Promise.resolve() : Promise.reject(new Error('数量应大于 0')) }]}><InputNumber stringMode style={{ width: '100%' }} /></Form.Item>
      <Form.Item label="选用依据 / 项目备注" name="note"><Input.TextArea rows={3} placeholder="记录选用理由、利旧情况或待确认条件" /></Form.Item>
    </Form>
  </Modal>;
}
