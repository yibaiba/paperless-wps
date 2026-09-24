import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Typography,
} from "antd";
import { api } from "../../shared/api";
import {
  AttributeEditor,
  AuthorFields,
  ROOT,
  required,
  useProducts,
  useVariants,
  variantOptions,
} from "./shared";
import { KnowledgeFields } from "./KnowledgeEditor";
export interface Draft {
  id: string;
  revision: number;
  kind: string;
  quotation: string;
  proposal: Record<string, unknown>;
  target_id: string | null;
  expected_revision: number;
  job_id: string;
  location: string;
  original: string;
  status: string;
}
export function DraftReview({
  draft,
  onClose,
}: {
  draft: Draft;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const products = useProducts(),
    variants = useVariants();
  const client = useQueryClient();
  const { message } = App.useApp();
  const [quotation, setQuotation] = useState(draft.quotation);
  const current =
    draft.kind === "product"
      ? products.data?.find((p) => p.id === draft.target_id)
      : variants.data?.find((v) => v.id === draft.target_id);
  const save = useMutation({
    mutationFn: (proposal: object) =>
      api(ROOT + "/extraction/drafts/" + draft.id, {
        method: "PUT",
        body: JSON.stringify({
          expected_revision: draft.revision,
          draft: {
            kind: draft.kind,
            quotation,
            proposal,
            target_id: draft.target_id,
            expected_revision: draft.expected_revision,
          },
        }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["configuration", "drafts"] });
      onClose();
    },
    onError: (e) => message.error(e.message),
  });
  return (
    <Modal
      open
      width={1200}
      title="核对 AI 草稿"
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="保存草稿修改"
      confirmLoading={save.isPending}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) minmax(0,1.4fr)",
          gap: 20,
        }}
      >
        <Card size="small" title={"原文 · " + draft.location}>
          <div className="config-source">{draft.original}</div>
          <Typography.Text strong>引用依据</Typography.Text>
          <Input.TextArea
            value={quotation}
            onChange={(e) => setQuotation(e.target.value)}
            rows={4}
          />
        </Card>
        <div>
          {current ? (
            <Alert
              className="section-bottom"
              title={`现有记录：${current.name} · v${current.revision}`}
              description={
                "attributes" in current
                  ? current.attributes
                      .map((a) => `${a.key}: ${a.value ?? "未知"} ${a.unit}`)
                      .join("；")
                  : current.model
              }
            />
          ) : (
            <Alert
              className="section-bottom"
              title={
                draft.target_id
                  ? "修改既有记录，需核对目标版本"
                  : "拟新增记录，不会自动覆盖产品资料"
              }
            />
          )}
          <Form
            form={form}
            layout="vertical"
            initialValues={draft.proposal}
            onFinish={(v) => save.mutate(v)}
          >
            {draft.kind === "knowledge" ? <KnowledgeFields /> : null}
            {draft.kind === "product" ? (
              <>
                <Form.Item name="name" label="名称" rules={required}>
                  <Input />
                </Form.Item>
                <Form.Item name="model" label="型号" rules={required}>
                  <Input />
                </Form.Item>
                <Space>
                  <Form.Item name="brand" label="品牌">
                    <Input />
                  </Form.Item>
                  <Form.Item name="category" label="类别">
                    <Input />
                  </Form.Item>
                </Space>
                <AuthorFields />
              </>
            ) : null}
            {draft.kind === "variant" ? (
              <>
                <Form.Item name="product_id" label="所属产品" rules={required}>
                  <Select
                    options={products.data?.map((p) => ({
                      value: p.id,
                      label: p.model + " · " + p.name,
                    }))}
                  />
                </Form.Item>
                <Form.Item name="name" label="配置名称" rules={required}>
                  <Input />
                </Form.Item>
                <Form.Item name="status" label="配置整理状态">
                  <Select
                    options={[
                      { value: "draft", label: "草稿" },
                      { value: "confirmed", label: "已确认" },
                    ]}
                  />
                </Form.Item>
                <AttributeEditor />
                {["series", "functions", "interfaces", "systems"].map(
                  (key, i) => (
                    <Form.Item
                      key={key}
                      name={key}
                      label={["系列", "功能", "接口", "适用系统"][i]}
                    >
                      <Select mode="tags" />
                    </Form.Item>
                  ),
                )}
                <AuthorFields />
              </>
            ) : null}
            {draft.kind === "source_link" ? (
              <>
                <Form.Item name="variant_id" label="关联的配置">
                  <Select options={variantOptions(variants.data)} />
                </Form.Item>
                <Form.Item name="items" hidden>
                  <Input />
                </Form.Item>
                <Typography.Paragraph>
                  将草稿中引用的原始来源关联到此配置；原资料不会删除。
                </Typography.Paragraph>
                <AuthorFields />
              </>
            ) : null}
            {draft.kind === "question" ? (
              <>
                <Alert
                  type="warning"
                  title="这是待确认问题，不能直接发布。补足资料后通过产品整理或搭配知识录入结论。"
                />
                <Form.Item name="question" label="问题内容">
                  <Input.TextArea rows={5} />
                </Form.Item>
              </>
            ) : null}
          </Form>
        </div>
      </div>
    </Modal>
  );
}
