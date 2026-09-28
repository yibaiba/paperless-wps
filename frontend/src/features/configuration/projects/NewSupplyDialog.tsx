import { Alert, Form, Input, Modal, Select } from "antd";
import type { SupplyAllocation } from "../types";
import { required } from "../shared";

export type SupplyChoice = Pick<SupplyAllocation, "source" | "evidence">;

export function NewSupplyDialog({ name, onConfirm, onClose }: {
  name: string; onConfirm: (choice: SupplyChoice) => void; onClose: () => void;
}) {
  const [form] = Form.useForm<SupplyChoice>();
  return <Modal open title="选择新设备的供货来源" onCancel={onClose} onOk={() => form.submit()}>
    <Alert type="info" title={name} description="已有硬件不会自动带入软件或授权资格。部分已有、部分采购可在加入后拆分数量。" />
    <Form form={form} layout="vertical" onFinish={onConfirm}>
      <Form.Item name="source" label="供货来源" rules={required}><Select options={[
        { value: "purchase", label: "本次采购" }, { value: "existing", label: "客户已有" }, { value: "unknown", label: "供货待确认" },
      ]} /></Form.Item>
      <Form.Item name="evidence" label="供货或授权依据" rules={required}><Input.TextArea /></Form.Item>
    </Form>
  </Modal>;
}
