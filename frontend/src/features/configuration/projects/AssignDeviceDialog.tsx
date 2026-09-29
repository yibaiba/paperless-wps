import { requirementDeviceIds, unlinkRoleDevice } from "./roleAllocations";
import { Alert, Modal, Select, Space, Typography } from 'antd';
import { useState } from 'react';
import type { Configuration } from '../types';

export function AssignDeviceDialog({ deviceId, configuration, onApply, onClose }: {
  deviceId: string; configuration: Configuration; onApply: (configuration: Configuration) => void; onClose: () => void;
}) {
  const device = configuration.devices.find((d) => d.id === deviceId)!;
  const [selected, setSelected] = useState<string[]>(configuration.requirements.filter((r) => requirementDeviceIds(r).includes(deviceId)).map((r) => r.id));
  const [error, setError] = useState('');
  return <Modal open title={`关联用途 · ${device.name}`} onCancel={onClose} onOk={() => {
    if (selected.length > 1 && Number(device.quantity) !== 1) { setError('跨角色共享设备必须是单台实例；请先拆分设备或核对数量。'); return; }
    onApply({ ...configuration, requirements: configuration.requirements.map((r) => selected.includes(r.id) ? requirementDeviceIds(r).includes(deviceId) ? r : { ...r, device_id: deviceId, allocations: [] } : unlinkRoleDevice(r, deviceId)) }); onClose();
  }}>
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Typography.Text>选择设备承担的角色。关联本身不代表兼容、容量或共享条件已通过。</Typography.Text>
      <Select mode="multiple" aria-label="设备承担角色" style={{ width: '100%' }} value={selected} onChange={setSelected}
        options={configuration.requirements.map((r) => ({ value: r.id, label: `${configuration.systems.find((s) => s.id === r.system_id)?.name} / ${r.role}`,
          disabled: requirementDeviceIds(r).length > 0 && !requirementDeviceIds(r).includes(deviceId) }))} />
      {!configuration.requirements.length ? <Alert type="info" title="请先在左侧添加系统和角色需求，再建立关联。" /> : null}
      {error ? <Alert type="error" title={error} /> : null}
    </Space>
  </Modal>;
}
