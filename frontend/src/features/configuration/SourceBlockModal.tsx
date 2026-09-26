import { useMutation, useQueryClient } from "@tanstack/react-query";
import { App, Form, Input, Modal } from "antd";
import { api } from "../../shared/api";
import { configurationKeys } from "./queryKeys";
import { AuthorFields, ROOT } from "./shared";

interface SourceRevision {
  id: string;
  link_revision: number;
}

export function SourceBlockModal({
  sources,
  onClose,
}: {
  sources: SourceRevision[];
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const client = useQueryClient();
  const { message } = App.useApp();
  const mutation = useMutation({
    mutationFn: (values: { reason: string; actor: string; evidence: string }) =>
      api(ROOT + "/source-blocks", {
        method: "POST",
        body: JSON.stringify({
          ...values,
          items: sources.map((source) => ({
            source_id: source.id,
            expected_revision: source.link_revision,
          })),
        }),
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: configurationKeys.all });
      message.success("已记录明确阻塞原因，原始资料保持不变");
      onClose();
    },
    onError: (error) => message.error(error.message),
  });
  return (
    <Modal
      open
      title={`标记 ${sources.length} 条来源为明确阻塞`}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={mutation.isPending}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) => mutation.mutate(values)}
      >
        <Form.Item
          name="reason"
          label="无法完成归属的原因"
          rules={[{ required: true, message: "请填写可继续处理的具体原因" }]}
        >
          <Input.TextArea
            rows={3}
            placeholder="例如：总表列错位，型号和产品名称无法从当前资料确认"
          />
        </Form.Item>
        <AuthorFields />
      </Form>
    </Modal>
  );
}
