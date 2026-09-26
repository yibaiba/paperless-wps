import { Form, Modal, Select, Table } from "antd";
import type { FormInstance } from "antd";
import type { Variant } from "../types";
import { AuthorFields, variantOptions } from "../shared";

export function SourceLinkModal({
  open,
  selectedCount,
  variants,
  form,
  loading,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  selectedCount: number;
  variants?: Variant[];
  form: FormInstance;
  loading: boolean;
  onCancel: () => void;
  onSubmit: (values: object) => void;
}) {
  return (
    <Modal
      title={`确认 ${selectedCount} 条来源属于同一具体配置`}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={loading}
    >
      <Form form={form} layout="vertical" onFinish={onSubmit}>
        <Form.Item name="variant_id" label="已确认配置" rules={[{ required: true }]}>
          <Select
            showSearch
            optionFilterProp="label"
            options={variantOptions(variants?.filter((variant) => variant.status === "confirmed"))}
          />
        </Form.Item>
        <AuthorFields />
      </Form>
    </Modal>
  );
}

export function CatalogHistoryModal({
  open,
  rows,
  variants,
  onClose,
}: {
  open: boolean;
  rows?: Record<string, unknown>[];
  variants?: Variant[];
  onClose: () => void;
}) {
  return (
    <Modal title="修订记录" open={open} onCancel={onClose} footer={null}>
      <Table
        rowKey="revision"
        dataSource={rows}
        columns={[
          { title: "版本", dataIndex: "revision" },
          {
            title: "关联配置",
            render: (_, row) =>
              row.variant_id
                ? (variants?.find((variant) => variant.id === row.variant_id)?.name ??
                  String(row.variant_id))
                : "—",
          },
          { title: "维护人", dataIndex: "actor" },
          { title: "依据", dataIndex: "evidence" },
          { title: "阻塞原因", dataIndex: "reason" },
        ]}
      />
    </Modal>
  );
}
