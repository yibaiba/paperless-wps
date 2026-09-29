import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Modal, Table } from 'antd';
import { api } from '../../../../shared/api';
import { updateRoot } from './types';
interface RecordPrice { id: string; revision: number; column: string; effective_date: string; amount: string | null; state: string; actor: string; evidence: string }
export function PriceHistory({ variantId }: { variantId: string }) {
  const [slot, setSlot] = useState<string>();
  const history = useQuery({ queryKey: ['catalog-updates', 'prices', variantId], enabled: !!variantId, queryFn: () => api<{ history: RecordPrice[] }>(`${updateRoot}/prices/${variantId}`) });
  const revisions = useQuery({ queryKey: ['catalog-updates', 'price-revisions', slot], enabled: !!slot, queryFn: () => api<RecordPrice[]>(`${updateRoot}/price-history/${slot}`) });
  const columns = [{ title: '价格列', dataIndex: 'column' }, { title: '生效日期', dataIndex: 'effective_date' }, { title: '金额', render: (_: unknown, p: RecordPrice) => p.state === 'inquiry' ? '待询价' : p.amount }, { title: '修订', dataIndex: 'revision' }, { title: '维护人', dataIndex: 'actor' }, { title: '依据', dataIndex: 'evidence' }];
  return <>
    {history.error ? <Alert type="error" title={history.error.message} /> : null}
    <Table<RecordPrice> size="small" rowKey="id" loading={history.isFetching} dataSource={history.data?.history} columns={[...columns, { title: '历史', render: (_, p) => <Button size="small" onClick={() => setSlot(p.id)}>查看修订</Button> }]} />
    <Modal open={!!slot} title="同日价格更正历史" width={900} footer={null} onCancel={() => setSlot(undefined)}>
      {revisions.error ? <Alert type="error" title={revisions.error.message} /> : null}
      <Table<RecordPrice> size="small" rowKey="revision" loading={revisions.isFetching} dataSource={revisions.data} columns={columns} />
    </Modal>
  </>;
}
