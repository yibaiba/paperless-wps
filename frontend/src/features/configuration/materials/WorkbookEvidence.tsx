import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Input, InputNumber, Select, Space, Table, Typography } from 'antd';
import { api } from '../../../shared/api';
import { ROOT } from '../shared';
import { configurationKeys } from '../queryKeys';
import type { EvidenceReference } from '../types';
import { WorkbookUpload } from './WorkbookUpload';
export type MaterialSegment = { id: string; location: string; text: string; anchor: string; merge_range?: string };
export type WorkbookMaterial = { id: string; revision: number; name: string; format: string; digest: string; ranges: { sheet: string; range: string }[]; segments: MaterialSegment[] };
export function WorkbookEvidence({ onReference }: { onReference: (reference: EvidenceReference) => void }) {
  const client = useQueryClient(); const [id, setId] = useState<string>(), [revision, setRevision] = useState(1);
  const [segment, setSegment] = useState<MaterialSegment>(), [quote, setQuote] = useState('');
  const materials = useQuery({ queryKey: configurationKeys.materials, queryFn: () => api<WorkbookMaterial[]>(ROOT + '/extraction/materials') });
  const document = useQuery({ queryKey: configurationKeys.materialRevision(id, revision), enabled: !!id,
    queryFn: () => api<WorkbookMaterial>(`${ROOT}/extraction/materials/${id}/revisions/${revision}`) });
  function select(value: string, version: number) { setId(value); setRevision(version); setSegment(undefined); setQuote(''); }
  const error = materials.error || document.error;
  const current = materials.data?.find(m => m.id === id);
  return <Space orientation="vertical" style={{ width: '100%' }}>
    {error && <Alert type="error" title={error.message} />}
    <Space wrap><WorkbookUpload onSaved={m => { void client.invalidateQueries({ queryKey: configurationKeys.materials }); select(m.id, m.revision); }} />
      {current && <WorkbookUpload previous={current} onSaved={m => { void client.invalidateQueries({ queryKey: configurationKeys.materials }); select(m.id, m.revision); }} />}</Space>
    <Select placeholder="选择已保存的工作簿说明" value={id} style={{ width: '100%' }} options={materials.data?.filter(m => m.format === 'xlsx').map(m => ({ value: m.id, label: m.name }))}
      onChange={value => select(value, materials.data!.find(m => m.id === value)!.revision)} />
    {id && <Space>固定修订<InputNumber min={1} precision={0} value={revision} onChange={value => value && select(id, value)} /><Typography.Text type="secondary">最新 v{current?.revision}；修改引用需明确选择修订</Typography.Text></Space>}
    <Table size="small" rowKey="id" loading={document.isFetching} dataSource={document.data?.segments.filter(s => s.text !== '')} pagination={{ pageSize: 6 }} columns={[
      { title: '位置', render: (_, s) => <>{s.location}{s.merge_range && <div>合并 {s.merge_range}，归属 {s.anchor}</div>}</> },
      { title: '原文', render: (_, s) => <Typography.Paragraph ellipsis={{ rows: 3, expandable: true }}>{s.text}</Typography.Paragraph> },
      { title: '引用', render: (_, s) => <Button onClick={() => { setSegment(s); setQuote(s.text); }}>选择原文</Button> },
    ]} />
    {segment && <><Input.TextArea aria-label="资料原文摘录" value={quote} onChange={event => setQuote(event.target.value)} rows={4} />
      <Button disabled={!quote.trim() || !segment.text.includes(quote) || document.isFetching} onClick={() => onReference({ material_id: id!, material_revision: revision, segment_id: segment.id, locator: segment.location, quote })}>引用到当前记录</Button>
      {quote && !segment.text.includes(quote) && <Alert type="error" title="摘录必须是此片段中的连续原文" />}</>}
  </Space>;
}
