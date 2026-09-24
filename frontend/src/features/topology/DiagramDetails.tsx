import {Alert, Button, Empty, Space, Table, Tabs, Tag, Typography} from 'antd';
import type {Diagram, Topology} from './types';
import {modeLabels, relationLabels} from './types';

interface Props {
  diagram: Diagram; models: Record<string, {model: string}>; saved?: Topology; dirty: boolean;
  onEdit: (id: string, kind: string) => void; onConvert: (id: string) => void; converting: boolean;
}
export function DiagramDetails({diagram, models, saved, dirty, onEdit, onConvert, converting}: Props) {
  const deviceNames = new Map(diagram.devices.map(d => [d.id, models[d.product_id]?.model ?? d.product_id]));
  return <Tabs items={[
    {key: 'devices', label: `设备 ${diagram.devices.length}`, children: <Table size="small" rowKey="id" dataSource={diagram.devices} scroll={{x: 700}}
      locale={{emptyText: <Empty description="点击「添加产品」或将绘图设备绑定到产品库，在这里维护数量和归属"/>}} columns={[
        {title: '产品 / 角色', render: (_, d) => <Space orientation="vertical" size={0}><Typography.Text strong>{deviceNames.get(d.id)}</Typography.Text><span>{d.role || '角色待填写'}</span></Space>},
        {title: '数量', dataIndex: 'quantity', width: 80},
        {title: '所在分组', render: (_, d) => diagram.groups.find(g => g.id === d.group_id)?.name ?? '未分组 / 共享区'},
        {title: '额外服务系统', render: (_, d) => d.serves_group_ids.map(id => diagram.groups.find(g => g.id === id)?.name).join('、') || '—'},
        {title: '操作', width: 110, fixed: 'right', render: (_, d) => <Button onClick={() => onEdit(d.id, 'device')}>编辑设备</Button>},
      ]}/>},
    {key: 'relations', label: `关系 ${diagram.relations.length}`, children: <>
      <Alert type="info" showIcon className="section-bottom" title="必配关系可生成全局草稿规则，启用前需确认适用范围。"
        description="草稿不会自动启用；之后修改拓扑不会同步改写规则。跨系统、共享容量和可选关系暂只记录，不直接转成数量规则。"/>
      <Table size="small" rowKey="id" dataSource={diagram.relations} scroll={{x: 820}} columns={[
        {title: '设备关系', render: (_, r) => `${deviceNames.get(r.source)} → ${deviceNames.get(r.target)}`},
        {title: '类型 / 参数', render: (_, r) => <Space orientation="vertical" size={2}><Tag color={r.kind === 'required' ? 'green' : undefined}>{relationLabels[r.kind]}</Tag>
          {r.kind === 'required' ? `${modeLabels[r.mode]}：${r.factor}` : r.kind === 'connection' ? `${r.source_port || '接口待填'} → ${r.target_port || '接口待填'} · ${r.cable || '线材待填'}${r.length_m ? ` · ${r.length_m} 米` : ''}` : null}</Space>},
        {title: '依据', dataIndex: 'evidence', width: 230},
        {title: '操作', width: 220, render: (_, r) => {
          const link = saved?.rules.find(item => item.relation_id === r.id);
          return <Space wrap><Button onClick={() => onEdit(r.id, 'relation')}>编辑关系</Button>
            {link ? <Tag>已生成 · 拓扑 v{link.topology_revision}</Tag> : r.kind === 'required' ? <Button disabled={dirty || !saved} loading={converting} onClick={() => onConvert(r.id)}>生成草稿规则</Button> : null}</Space>;
        }},
      ]}/>
      {dirty ? <Typography.Text type="secondary">先保存拓扑，再生成规则。</Typography.Text> : null}
    </>},
    {key: 'groups', label: `系统 ${diagram.groups.length}`, children: <Table size="small" rowKey="id" dataSource={diagram.groups} columns={[
      {title: '系统名称', dataIndex: 'name'}, {title: '方案产品线', dataIndex: 'product_line'},
      {title: '操作', render: (_, g) => <Button onClick={() => onEdit(g.id, 'group')}>编辑分组</Button>},
    ]}/>},
    {key: 'bom', label: '设备清单', children: <>
      <Alert className="section-bottom" type={dirty ? 'warning' : 'info'} title={saved ? `以下为已保存 v${saved.revision} 的设备汇总${dirty ? '，当前修改尚未计入' : ''}` : '保存拓扑后生成设备汇总'}
        description="按产品来源记录和所在分组合并数量；共享服务关系不重复计数。接线及可选关系不会自动增加物料，此表尚不含价格。"/>
      <Table size="small" rowKey={r => `${r.product_id}:${r.group_name}`} dataSource={saved?.bom ?? []} scroll={{x: 650}} columns={[
        {title: '型号', render: (_, r) => r.product.model}, {title: '名称', render: (_, r) => r.product.name},
        {title: '系统', dataIndex: 'group_name'}, {title: '数量', dataIndex: 'quantity'}, {title: '单位', render: (_, r) => r.product.unit},
        {title: '来源', render: (_, r) => `${r.product.sheet} · 第 ${r.product.row} 行`},
      ]}/>
    </>},
  ]}/>;
}
