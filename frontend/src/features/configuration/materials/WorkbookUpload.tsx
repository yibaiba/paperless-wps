import { useRef, useState } from 'react';
import { Alert, App, Button, Drawer, Form, Input, Select, Space, Table, Upload } from 'antd';
import { api } from '../../../shared/api';
import { AuthorFields, ROOT, required } from '../shared';
import type { WorkbookMaterial } from './WorkbookEvidence';

type Sheet = { name: string; rows: string[][]; merges: { range: string }[] };
type Preview = { digest: string; name: string; sheets: Sheet[] };
export function WorkbookUpload({ previous, onSaved }: { previous?: WorkbookMaterial; onSaved: (material: WorkbookMaterial) => void }) {
  const [open, setOpen] = useState(false), [preview, setPreview] = useState<Preview>(), [file, setFile] = useState<File>();
  const [sheetName, setSheet] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const request = useRef<{ payload: string; id: string } | undefined>(undefined);
  const selection = useRef(0);
  const [form] = Form.useForm(); const { message } = App.useApp();
  const sheet = preview?.sheets.find(s => s.name === sheetName);
  async function read(value: File) {
    const sequence = ++selection.current;
    setBusy(true); setError(''); setPreview(undefined); setFile(undefined);
    try { const body = new FormData(); body.append('file', value); const result = await api<Preview>(ROOT + '/extraction/materials/xlsx/preview', { method: 'POST', body });
      if (sequence !== selection.current) return;
      setPreview(result); setFile(value); setSheet(result.sheets[0]?.name ?? '');
      form.setFieldsValue({ name: previous?.name ?? value.name, ranges: previous?.ranges ?? [{ sheet: result.sheets[0]?.name, range: '' }] });
    } catch (e) { if (sequence === selection.current) setError((e as Error).message); } finally { if (sequence === selection.current) setBusy(false); }
  }
  async function save(values: Record<string, unknown>) {
    if (!file || !preview) return;
    setBusy(true); setError('');
    try { const payload = JSON.stringify({ ...values, digest: preview.digest, material_id: previous?.id, revision: previous?.revision });
      if (request.current?.payload !== payload) request.current = { payload, id: crypto.randomUUID() };
      const body = new FormData(); body.append('file', file); body.append('options', JSON.stringify({ ...values, digest: preview.digest,
      operation_id: request.current.id, ...(previous ? { material_id: previous.id, expected_revision: previous.revision } : {}) }));
      const result = await api<WorkbookMaterial>(ROOT + '/extraction/materials/xlsx', { method: 'POST', body });
      onSaved(result); setOpen(false); message.success('资料范围已保存，未调用模型');
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <><Button onClick={() => setOpen(true)}>{previous ? '上传此资料新修订' : '保存工作簿说明'}</Button>
    <Drawer title="选择工作簿原文范围" open={open} width={950} onClose={() => setOpen(false)}>
      <Alert type="info" title="资料原文独立保存，不增加产品来源；公式仅作为文字依据。" />
      {error && <Alert type="error" title={error} />}
      <Upload accept=".xlsx" showUploadList={false} beforeUpload={value => { void read(value); return false; }}><Button loading={busy}>选择 XLSX</Button></Upload>
      {preview && <><Select value={sheetName} onChange={setSheet} style={{ width: 360 }} options={preview.sheets.map(s => ({ value: s.name, label: s.name }))} />
        <Table size="small" rowKey="row" scroll={{ x: 1500, y: 240 }} pagination={{ pageSize: 10 }} dataSource={sheet?.rows.map((cells, index) => ({ row: index + 1, cells }))}
          columns={[{ title: '行', dataIndex: 'row', width: 60 }, ...Array.from({ length: Math.max(0, ...(sheet?.rows.map(r => r.length) ?? [])) }, (_, i) => ({ title: columnName(i), width: 180, render: (_: unknown, r: { cells: string[] }) => r.cells[i] }))]} />
        <div>合并区域：{sheet?.merges.map(m => m.range).join('、') || '无'}</div>
        <Form form={form} layout="vertical" onFinish={save}>
          <Form.Item name="name" label="资料名称" rules={required}><Input /></Form.Item>
          <Form.List name="ranges">{(fields, { add, remove }) => <>{fields.map(f => <Space key={f.key} align="baseline">
            <Form.Item name={[f.name, 'sheet']} rules={required}><Select style={{ width: 260 }} options={preview.sheets.map(s => ({ value: s.name, label: s.name }))} /></Form.Item>
            <Form.Item name={[f.name, 'range']} rules={required}><Input placeholder="例如 D5:E8" /></Form.Item><Button onClick={() => remove(f.name)}>移除范围</Button>
          </Space>)}<Button onClick={() => add({ sheet: sheetName, range: '' })}>增加范围</Button></>}</Form.List>
          <AuthorFields /><Button type="primary" htmlType="submit" loading={busy}>保存所选原文</Button>
        </Form></>}
    </Drawer></>;
}
function columnName(index: number): string { let name = ''; for (let n = index + 1; n; n = Math.floor((n - 1) / 26)) name = String.fromCharCode(65 + (n - 1) % 26) + name; return name; }
