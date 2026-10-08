import { useState } from 'react';
import { Alert, Spin, Tabs } from 'antd';
import { DeploymentForm } from './forms/DeploymentForm';
import type { Checked, Configuration, Deployment, IssueAction } from '../types';
import { deviceOperation, type Operation } from './drafts/operations';
import { DeviceUsagePanel } from './DeviceUsagePanel';

interface Props {
  device: Deployment;
  context: Configuration;
  requiresSupply: boolean;
  checked?: Checked;
  draftId?: string;
  draftRevision?: number;
  stale: boolean;
  onAction: (action: IssueAction) => void;
  onRecheck: () => void;
  execute: (operations: Operation[]) => Promise<Checked>;
  onApply: (checked: Checked) => void;
  onClose: () => void;
}

export function DeviceInspector({ device, context, requiresSupply, execute, onApply, onClose, checked, draftId, draftRevision, stale, onAction, onRecheck }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; context: Configuration }>();
  const apply = async (operation: Operation, close = false) => {
    setBusy(true); setError(undefined);
    try {
      const checked = await execute([operation]);
      onApply(checked);
      if (close) onClose();
    } catch (cause) {
      setError({ message: cause instanceof Error ? cause.message : String(cause), context });
    } finally { setBusy(false); }
  };
  return <Spin spinning={busy}>
    {error?.context === context ? <Alert type="error" showIcon title={error.message} /> : null}
    <Tabs items={[{ key: 'properties', label: '设备属性', children: <DeploymentForm device={device} requiresSupply={requiresSupply} onClose={onClose}
      disabled={busy}
      onApply={value => {
        const operation = deviceOperation(device, value);
        if (operation) void apply(operation);
      }}
      onDelete={() => void apply({ action: 'remove', collection: 'devices', id: device.id }, true)}
      onClone={supply => {
        const id = crypto.randomUUID();
        void apply({ action: 'device_clone', source_device_id: device.id, new_device_id: id,
          supply_allocations: supply ? [{ id: crypto.randomUUID(), device_id: id, quantity: device.quantity, ...supply }] : [],
        }, true);
      }} /> }, { key: 'usage', label: '用途与分配', children: <DeviceUsagePanel deviceId={device.id}
        configuration={context} checked={checked} draftId={draftId} draftRevision={draftRevision}
        stale={stale} onAction={onAction} onRecheck={onRecheck} /> }]} />
  </Spin>;
}
