import { Button, Input, Select, Space, Table, Typography } from 'antd';
import { useState } from 'react';
import type { Configuration } from '../../types';
import type { ImportRow } from './model';

export function ImportAssignment({ rows, configuration, onChange }: {
  rows: ImportRow[]; configuration: Configuration; onChange: (rows: ImportRow[]) => void;
}) {
  const [system, setSystem] = useState<string>();
  const update = (row: ImportRow, patch: Partial<ImportRow>) => onChange(rows.map((r) => r.id === row.id ? { ...r, ...patch } : r));
  const systemOptions = configuration.systems.map((s) => ({ value: s.id,
    label: `${configuration.rooms.find((r) => r.id === s.room_id)?.name ?? '未指定房间'} / ${s.name} / ${s.kind}` }));
  return <Space orientation="vertical" style={{ width: '100%' }}>
    <Typography.Title level={5}>业务归属（可保留待关联）</Typography.Title>
    <Space><Select aria-label="批量归属系统" allowClear placeholder="选择已有房间 / 系统版本" value={system} onChange={setSystem} style={{ width: 350 }} options={systemOptions} />
      <Button onClick={() => onChange(rows.map((r) => r.include ? { ...r, systemId: system, requirementId: undefined } : r))}>应用到所选行</Button></Space>
    <Typography.Text type="secondary">可使用“本批新增房间 / 系统”，整批确认后才应用。关联已有设备只建立用途，不改数量、价格或备注。</Typography.Text>
    <Table<ImportRow> rowKey="id" size="small" dataSource={rows.filter((r) => r.include)} pagination={{ pageSize: 5 }} scroll={{ x: 1100 }} columns={[
      { title: '原表行', width: 170, render: (_, row) => `${row.sourceRow} · ${row.model}` },
      { title: '新增或关联已有设备', width: 270, render: (_, row) => <Select allowClear placeholder="新增独立设备" value={row.existingDeviceId} style={{ width: '100%' }}
        onChange={(existingDeviceId) => update(row, { existingDeviceId })} options={configuration.devices.map((d) => ({ value: d.id, label: `${d.name} · ${d.id.slice(0, 8)} · ${d.quantity}` }))} /> },
      { title: '房间 / 系统版本', width: 300, render: (_, row) => <Select allowClear placeholder="待关联" value={row.systemId} options={systemOptions} style={{ width: '100%' }}
        onChange={(systemId) => update(row, { systemId, requirementId: undefined })} /> },
      { title: '角色需求', width: 330, render: (_, row) => <Space orientation="vertical" style={{ width: '100%' }}>
        <Select allowClear disabled={!row.systemId} placeholder="关联已有角色，或填写新角色" value={row.requirementId} style={{ width: 300 }}
          onChange={(requirementId) => update(row, { requirementId })} options={configuration.requirements.filter((r) => r.system_id === row.systemId).map((r) => ({ value: r.id, label: `${r.role}${r.device_id ? '（已选设备）' : ''}` }))} />
        {!row.requirementId ? <Input disabled={!row.systemId} placeholder="新角色名称，例如服务端软件；不确定可留空" value={row.roleName} onChange={(e) => update(row, { roleName: e.target.value })} /> : null}
      </Space> },
    ]} />
  </Space>;
}
