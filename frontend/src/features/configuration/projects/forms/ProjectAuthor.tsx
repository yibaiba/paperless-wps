import { Form, Modal } from "antd";
import type { Configuration } from "../../types";
import { AuthorFields } from "../../shared";

export function ProjectAuthor({
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
    <Modal open title="项目维护信息" onCancel={onClose} onOk={() => form.submit()}>
      <Form
        form={form}
        layout="vertical"
        initialValues={configuration}
        onFinish={(values) => {
          onApply({ ...configuration, actor: values.actor, evidence: values.evidence });
          onClose();
        }}
      >
        <AuthorFields />
      </Form>
    </Modal>
  );
}
