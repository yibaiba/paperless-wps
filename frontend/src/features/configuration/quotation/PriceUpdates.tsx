import { useRef, useState } from 'react';
import { Alert, Button, Drawer, Input, Space, Table, Tag, Typography } from 'antd';
import { api } from '../../../shared/api';
import { beijingDate } from '../catalog/updates/types';
import { useSheetEditing, type SheetContext } from './sheet/useSheetEditing';
interface PriceRow {
  device_id: string; old_unit_price: string | null; difference: string | null; before_amount: string | null; after_amount: string | null;
  protected: boolean; legacy: boolean; issues: string[];
  price: { id: string; revision: number; amount: string | null; effective_date: string; evidence: string; state: string } | null;
}
interface PricePreview { rows: PriceRow[]; fingerprint: string; adoption_date: string }
export function PriceUpdates({ context, onClose }: { context: SheetContext; onClose: () => void }) {
  const [date, setDate] = useState(context.configuration.quotation?.price_adoption_date || beijingDate());
  const [preview, setPreview] = useState<PricePreview>(), [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [origin, setOrigin] = useState(context.draftVersion);
  const live = useRef(context); live.current = context;
  const editor = useSheetEditing(context);
  const stale = origin !== context.draftVersion;
  async function check() {
    setBusy(true); setError(''); setSelected([]); setPreview(undefined);
    const version = context.draftVersion;
    try {
      const result = await api<PricePreview>('/catalog-updates/project-price-preview', { method: 'POST', body: JSON.stringify({ configuration: context.configuration, adoption_date: date }) });
      if (live.current.draftVersion !== version) throw new Error('项目已修改，请重新检查价格更新');
      setPreview(result); setOrigin(version);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const known = selected.map(id => preview?.rows.find(r => r.device_id === id));
  // Display server-rounded differences as integer cents, without floating point summation.
  const delta = known.every(r => r?.difference != null) ? known.reduce((sum, r) => {
    const text = r!.difference!, negative = text.startsWith('-'), [whole, fraction = ''] = text.replace('-', '').split('.');
    return sum + (negative ? -1n : 1n) * (BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0')));
  }, 0n) : null;
  const totalText = delta === null ? '存在原价缺失，无法比较完整差额' : `${delta < 0n ? '-' : ''}${(delta < 0n ? -delta : delta) / 100n}.${String((delta < 0n ? -delta : delta) % 100n).padStart(2, '0')}`;
  return <Drawer open title="检查价格更新" size={1000} onClose={onClose}>
    <Space orientation="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="info" title="只更新明确选择的报价行" description="人工调整价和导入价不默认覆盖。设备参数、数量、知识版本和历史报价保持原样。" />
      <Space><Typography.Text>价格采用日期</Typography.Text><Input type="date" aria-label="价格采用日期" value={date} onChange={e => { setDate(e.target.value); setPreview(undefined); setSelected([]); }} />
        <Button loading={busy} disabled={!date || editor.busy} onClick={() => void check()}>查询生效价格</Button></Space>
      {error || editor.error ? <Alert type="error" title={error || editor.error} /> : null}
      {stale && preview ? <Alert type="warning" title="项目已修改，请重新查询后采用" /> : null}
      <Table<PriceRow> rowKey="device_id" dataSource={preview?.rows} pagination={{ pageSize: 20 }} rowSelection={{ selectedRowKeys: selected, onChange: keys => setSelected(keys.map(String)), getCheckboxProps: r => ({ disabled: !!r.issues.length || stale || editor.busy }) }} columns={[
        { title: '设备', render: (_, r) => context.configuration.devices.find(d => d.id === r.device_id)?.name },
        { title: '已用单价', render: (_, r) => <>{r.old_unit_price ?? '缺价'}<div><Tag>{r.protected ? '人工 / 导入价' : r.legacy ? '旧来源价' : '版本价格'}</Tag></div></> },
        { title: '可用新价', render: (_, r) => r.price?.state === 'inquiry' ? '待询价' : r.price?.amount ?? '未发布' },
        { title: '本次采购金额差额', dataIndex: 'difference', render: v => v ?? '待确认' },
        { title: '依据与问题', render: (_, r) => <>{r.price?.effective_date}<div>{r.price?.evidence}</div>{r.issues.map(i => <div key={i}>{i}</div>)}</> },
      ]} />
      <Typography.Text>所选 {selected.length} 行金额变化：{totalText}</Typography.Text>
      <Button type="primary" loading={editor.busy} disabled={!selected.length || stale || busy} onClick={async () => {
        if (!preview) return;
        const applied = await editor.execute([{ action: 'price_versions_adopt', adoption_date: date, fingerprint: preview.fingerprint,
          items: selected.map(id => { const p = preview.rows.find(r => r.device_id === id)!.price!; return { device_id: id, price: { id: p.id, revision: p.revision } }; }) }], true);
        if (applied) onClose();
      }}>确认采用所选价格</Button>
    </Space>
  </Drawer>;
}
