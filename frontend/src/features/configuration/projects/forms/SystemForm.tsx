import { Form, Input, Modal } from "antd";
import type { Configuration } from "../../types";
import { SystemTypeInput } from "../../SystemTypeInput";
import { required } from "../../shared";

export function SystemForm({
  configuration,
  onApply,
  onClose,
}: {
  configuration: Configuration;
  onApply: (configuration: Configuration) => void;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  return (
    <Modal open title="添加房间与系统" onCancel={onClose} onOk={() => form.submit()}>
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) => {
          const existing = configuration.rooms.find((room) => room.name === values.room);
          const room = existing ?? { id: crypto.randomUUID(), name: values.room };
          onApply({
            ...configuration,
            rooms: existing ? configuration.rooms : [...configuration.rooms, room],
            systems: [
              ...configuration.systems,
              {
                id: crypto.randomUUID(),
                room_id: room.id,
                name: values.name,
                kind: values.kind,
              },
            ],
          });
          onClose();
        }}
      >
        <Form.Item name="room" label="房间名称" rules={required}>
          <Input placeholder="一楼会议室" />
        </Form.Item>
        <Form.Item name="name" label="系统名称" rules={required}>
          <Input placeholder="一楼无纸化" />
        </Form.Item>
        <Form.Item
          name="kind"
          label="系统 / 方案版本"
          rules={required}
          extra="选择具体版本；Windows、麒麟等运行环境在角色需求中填写。"
        >
          <SystemTypeInput />
        </Form.Item>
      </Form>
    </Modal>
  );
}
