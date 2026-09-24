import { Form, Input, Modal, Select } from "antd";
import type { Knowledge } from "./types";
import { AuthorFields, useVariants, variantOptions } from "./shared";
export function knowledgePayload(item: Knowledge) {
  return Object.fromEntries(
    Object.entries(item).filter(
      ([key]) => !["id", "revision", "updated_at"].includes(key),
    ),
  );
}
export function KnowledgeBatch({
  selected,
  onSave,
  onClose,
  busy,
}: {
  selected: Knowledge[];
  onSave: (items: unknown[]) => void;
  onClose: () => void;
  busy: boolean;
}) {
  const [form] = Form.useForm();
  const variants = useVariants();
  return (
    <Modal
      open
      title={`批量编辑 ${selected.length} 条搭配知识`}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={busy}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) =>
          onSave(
            selected.map((item) => ({
              id: item.id,
              expected_revision: item.revision,
              payload: {
                ...knowledgePayload(item),
                actor: values.actor,
                evidence: values.evidence,
                ...(values.status ? { status: values.status } : {}),
                ...(values.system ? { system: values.system } : {}),
                ...(values.role ? { role: values.role } : {}),
                selector: {
                  ...item.selector,
                  exclude_variant_ids: [
                    ...new Set([
                      ...item.selector.exclude_variant_ids,
                      ...(values.exclude ?? []),
                    ]),
                  ],
                },
              },
            })),
          )
        }
      >
        <Form.Item name="status" label="统一状态（留空保持原值）">
          <Select
            allowClear
            options={[
              { value: "draft", label: "草稿" },
              { value: "confirmed", label: "已确认" },
              { value: "disabled", label: "停用" },
            ]}
          />
        </Form.Item>
        <Form.Item name="system" label="统一系统类型（留空保持原值）">
          <Select
            allowClear
            options={["无纸化", "会议预约"].map((value) => ({
              value,
              label: value,
            }))}
          />
        </Form.Item>
        <Form.Item name="role" label="统一角色（留空保持原值）">
          <Input />
        </Form.Item>
        <Form.Item name="exclude" label="追加排除的具体配置">
          <Select mode="multiple" options={variantOptions(variants.data)} />
        </Form.Item>
        <AuthorFields />
      </Form>
    </Modal>
  );
}
