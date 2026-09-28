import { Alert, Form, Input, InputNumber, Modal } from 'antd';
import type { Deployment } from '../../types';
import type { EditOperation } from './model';

export function DeviceSettings({ device, section, busy, onClose, onApply }: {
  device: Deployment; section: string; busy: boolean; onClose: () => void;
  onApply: (operations: EditOperation[]) => void;
}) {
  const [form] = Form.useForm();
  return <Modal open title={`部署与报价备注 · ${device.name}`} onCancel={onClose} onOk={() => form.submit()} confirmLoading={busy}>
    <Alert type="info" showIcon title="报价表数量为本次采购量" description="修改部署数量后，请通过供货面板分配采购、客户已有和待定数量。" />
    <Form form={form} layout="vertical" initialValues={{ quantity: device.quantity, note: device.note, section }} onFinish={(fields) => onApply([
      { action: 'device_patch', device_id: device.id, quantity: String(fields.quantity), note: fields.note ?? '' },
      { action: 'section_set', device_id: device.id, section: fields.section ?? '' },
    ])}>
      <Form.Item label="部署数量" name="quantity" rules={[{ required: true }, { validator: (_, value) => /^\d+(?:\.\d+)?$/.test(String(value)) && /[1-9]/.test(String(value)) ? Promise.resolve() : Promise.reject(new Error('请输入大于零的数量')) }]}><InputNumber stringMode style={{ width: '100%' }} /></Form.Item>
      <Form.Item label="报价分区（留空按服务系统）" name="section"><Input /></Form.Item>
      <Form.Item label="报价备注" name="note"><Input.TextArea rows={4} /></Form.Item>
    </Form>
  </Modal>;
}
