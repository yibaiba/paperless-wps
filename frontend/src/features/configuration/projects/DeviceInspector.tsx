import { useState } from 'react';
import { Alert, Spin } from 'antd';
import { DeploymentForm } from './forms/DeploymentForm';
import type { Checked, Configuration, Deployment } from '../types';
import { deviceOperation, type Operation } from './drafts/operations';

interface Props {
  device: Deployment;
  context: Configuration;
  requiresSupply: boolean;
  execute: (operations: Operation[]) => Promise<Checked>;
  onApply: (checked: Checked) => void;
  onClose: () => void;
}

export function DeviceInspector({ device, context, requiresSupply, execute, onApply, onClose }: Props) {
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
    <DeploymentForm device={device} requiresSupply={requiresSupply} onClose={onClose}
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
      }} />
  </Spin>;
}
