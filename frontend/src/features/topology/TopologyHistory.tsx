import {useQuery} from '@tanstack/react-query';
import {Alert, Collapse, Drawer, Spin, Table, Typography} from 'antd';
import {api} from '../../shared/api';
import {modeLabels, relationLabels} from './types';
import type {Topology} from './types';

export function TopologyHistory({id, onClose}: {id: string; onClose: () => void}) {
  const history = useQuery({queryKey: ['topology-history', id], staleTime: 0,
    queryFn: () => api<(Topology & {created_at: string})[]>(`/topologies/${id}/history`)});
  return <Drawer open title="拓扑版本记录" size={760} onClose={onClose}>
    {history.isLoading ? <Spin/> : null}
    {history.error ? <Alert type="error" title={history.error.message}/> : null}
    <Collapse items={history.data?.map(item => {
      const model = (deviceId: string) => item.products[item.devices.find(d => d.id === deviceId)!.product_id].model;
      return {key: item.revision,
        label: `v${item.revision} · ${item.actor} · ${new Date(item.created_at).toLocaleString()}`,
        children: <><Typography.Paragraph>{item.name} · {item.devices.length} 个设备节点 · {item.relations.length} 条关系</Typography.Paragraph>
          <Table size="small" rowKey={r => `${r.product_id}:${r.group_name}`} pagination={false} dataSource={item.bom} columns={[
            {title: '型号', render: (_, r) => r.product.model}, {title: '所在系统', dataIndex: 'group_name'}, {title: '数量', dataIndex: 'quantity'},
          ]}/>
          <Table className="section-gap" size="small" rowKey="id" pagination={false} dataSource={item.relations} columns={[
            {title: '关系', render: (_, r) => `${model(r.source)} → ${model(r.target)} · ${relationLabels[r.kind]}`},
            {title: '参数', render: (_, r) => r.kind === 'required' ? `${modeLabels[r.mode]} ${r.factor}` : r.kind === 'connection' ? `${r.source_port} → ${r.target_port} / ${r.cable}${r.length_m ? ` / ${r.length_m} 米` : ''}` : '—'},
            {title: '依据', dataIndex: 'evidence'},
          ]}/></>,
      };
    })}/>
  </Drawer>;
}
