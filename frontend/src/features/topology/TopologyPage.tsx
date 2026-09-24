import {useQuery} from '@tanstack/react-query';
import {Alert, Button, Card, Empty, Spin, Table} from 'antd';
import {useNavigate, useParams} from 'react-router-dom';
import {api} from '../../shared/api';
import {PageHeader} from '../../shared/PageHeader';
import {TopologyEditor} from './TopologyEditor';
import type {Topology, TopologySummary} from './types';
import './topology.css';

export default function TopologyPage() {
  const {topologyId} = useParams();
  const navigate = useNavigate();
  const list = useQuery({queryKey: ['topologies'], queryFn: () => api<TopologySummary[]>('/topologies')});
  const detail = useQuery({queryKey: ['topology', topologyId], enabled: !!topologyId && topologyId !== 'new',
    queryFn: () => api<Topology>(`/topologies/${topologyId}`)});
  return <>
    <PageHeader title="方案拓扑" description="从产品库搭建系统，记录设备角色、配套关系和接线依据。"
      actions={!topologyId ? <Button type="primary" onClick={() => navigate('/topologies/new')}>新建拓扑</Button> : undefined}/>
    {list.error || detail.error ? <Alert className="section-bottom" type="error" title={(list.error || detail.error)?.message}/> : null}
    {!topologyId ? <Card><Table<TopologySummary> rowKey="id" dataSource={list.data} loading={list.isLoading}
      locale={{emptyText: <Empty description="新建一个方案，从产品库添加真实设备，再设置系统和搭配关系。"/>}}
      columns={[
        {title: '方案名称', dataIndex: 'name'}, {title: '版本', render: (_, r) => `v${r.revision}`},
        {title: '设备节点', dataIndex: 'device_count'},
        {title: '操作', render: (_, r) => <Button onClick={() => navigate(`/topologies/${r.id}`)}>打开拓扑</Button>},
      ]}/></Card> : topologyId === 'new' || detail.data ? <TopologyEditor key={topologyId} initial={detail.data}
        onClose={() => navigate('/topologies')} onCreated={id => navigate(`/topologies/${id}`, {replace: true})}/> : detail.isLoading ? <Spin/> : null}
  </>;
}
