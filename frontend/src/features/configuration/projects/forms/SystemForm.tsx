import { Form, Input, Modal, Select } from "antd";
import type { Configuration } from "../../types";
import { SystemTypeInput } from "../../SystemTypeInput";
import { required } from "../../shared";

import { useDefinitions } from "../../knowledge/useDefinitions";

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
  const definitions = useDefinitions();
  const definitionId = Form.useWatch("definition_id", form);
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
                definition_id: values.definition_id ?? "",
                knowledge_package_id: values.knowledge_package_id ?? "",
                features: [],
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
        <Form.Item name="definition_id" label="已维护的系统定义"><Select allowClear
          options={definitions.data?.definitions.map((d) => ({ value: d.id, label: d.name }))}
          onChange={(id) => { form.setFieldValue("kind", definitions.data?.definitions.find((d) => d.id === id)?.name); form.setFieldValue("knowledge_package_id", undefined); }} /></Form.Item>
        <Form.Item name="knowledge_package_id" label="发布的知识包"><Select allowClear options={definitions.data?.packages.filter((p) => p.system_definition_id === definitionId).map((p) => ({ value: p.id, label: `${p.name} · ${p.branch} · v${p.revision}` }))} /></Form.Item>
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
