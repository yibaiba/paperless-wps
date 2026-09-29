import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Form, Input, Modal, Select, Upload } from 'antd';
import { api } from '../../../../shared/api';
import type { CatalogImport } from '../../../../shared/types';
import { AuthorFields, required, useVariants } from '../../shared';
import { type Batch, updateRoot } from './types';
export function CreateUpdate({ onClose, onCreated }: { onClose: () => void; onCreated: (batch: Batch) => void }) {
  const [form] = Form.useForm();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [receipt, setReceipt] = useState<{ body: string; key: string }>();
  const imports = useQuery({ queryKey: ['imports'], queryFn: () => api<CatalogImport[]>('/imports') });
  const variants = useVariants();
  const selected = Form.useWatch('import_id', form);
  async function submit(values: object) {
    setBusy(true); setError('');
    try { const body = JSON.stringify(values); const key = receipt?.body === body ? receipt.key : crypto.randomUUID(); setReceipt({ body, key }); onCreated(await api<Batch>(updateRoot, { method: 'POST', body: JSON.stringify({ ...values, operation_id: key }) })); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <Modal open title="建立产品与价格更新草稿" onCancel={onClose} onOk={() => form.submit()} confirmLoading={busy}>
    {error ? <Alert type="error" title={error} /> : null}
    <Form form={form} layout="vertical" onFinish={submit} initialValues={{ name: '', variant_ids: [], sheets: [] }}>
      <Form.Item name="name" label="本次变更名称" rules={required}><Input placeholder="例如：十月产品价格更新" /></Form.Item>
      <Form.Item name="import_id" label="新版 Excel（不选则人工维护）"><Select allowClear options={imports.data?.filter(i => i.source_kind !== "manual").map(i => ({ value: i.id, label: i.filename }))} /></Form.Item>
      <Upload showUploadList={false} accept=".xlsx" beforeUpload={async (file) => {
        setBusy(true); setError('');
        try { const body = new FormData(); body.append('file', file); const result = await api<CatalogImport>('/imports', { method: 'POST', body }); await imports.refetch(); form.setFieldValue('import_id', result.id); }
        catch (e) { setError((e as Error).message); } finally { setBusy(false); }
        return false;
      }}><Button loading={busy}>上传新版工作簿</Button></Upload>
      {selected ? <><Form.Item name="baseline_import_id" label="对比基准（不选则跨历史来源比较）"><Select allowClear options={imports.data?.filter(i => i.id !== selected && i.source_kind !== "manual").map(i => ({ value: i.id, label: i.filename }))} /></Form.Item>
        <Form.Item name="sheets" label="工作表范围（空为全部）"><Select mode="multiple" options={imports.data?.find(i => i.id === selected)?.sheets.map(s => ({ value: s, label: s }))} /></Form.Item></> : null}
      <Form.Item name="variant_ids" label="产品配置范围（空为全部）"><Select mode="multiple" showSearch optionFilterProp="label" options={variants.data?.map(v => ({ value: v.id, label: `${v.product.model} · ${v.name}` }))} /></Form.Item>
      <AuthorFields />
    </Form>
  </Modal>;
}
