import { Alert, App, Form, Modal, Table } from "antd";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../shared/api";
import { AuthorFields, ROOT } from "./shared";
interface Source {
  id: string;
  link_revision: number;
  model: string;
  name: string;
  sheet: string;
  row: number;
}
export function IndependentSources({
  sources,
  onClose,
}: {
  sources: Source[];
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const client = useQueryClient(),
    { message } = App.useApp();
  const save = useMutation({
    mutationFn: (values: object) =>
      api(ROOT + "/independent-sources", {
        method: "POST",
        body: JSON.stringify({
          ...values,
          items: sources.map((s) => ({
            source_id: s.id,
            expected_revision: s.link_revision,
          })),
        }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["configuration"] });
      message.success("已分别建立独立配置，参数缺失仍为未知");
      onClose();
    },
    onError: (e) => message.error(e.message),
  });
  return (
    <Modal
      open
      width={850}
      title={`确认 ${sources.length} 条来源分别为独立配置`}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={save.isPending}
      okText="确认各自独立并记录归属"
    >
      <Alert
        type="info"
        title="每条来源各建一个产品和配置，不按型号合并"
        description="只确认来源归属。原始参数、价格与备注继续保留；结构化参数尚未提取，搭配关系仍需单独确认。已有归属的记录将保留变更历史。"
      />
      <Table
        rowKey="id"
        size="small"
        dataSource={sources}
        columns={[
          { title: "型号", dataIndex: "model" },
          { title: "名称", dataIndex: "name" },
          {
            title: "原始出处",
            render: (_, s) => `${s.sheet} · 第 ${s.row} 行`,
          },
        ]}
      />
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <AuthorFields />
      </Form>
    </Modal>
  );
}
