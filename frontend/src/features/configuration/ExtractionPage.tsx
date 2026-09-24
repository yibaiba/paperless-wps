import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Typography,
  Upload,
} from "antd";
import { api } from "../../shared/api";
import type { CatalogImport, Product } from "../../shared/types";
import {
  AuthorFields,
  ROOT,
  Status,
  required,
  useVariants,
  useProducts,
  variantOptions,
} from "./shared";
import { ModelSettings } from "./ModelSettings";
import { DraftReview, type Draft } from "./DraftReview";
import "./configuration.css";
interface Material {
  id: string;
  name: string;
  format: string;
  segments: { location: string; text: string }[];
}
interface Job {
  id: string;
  status: string;
  error: string;
  segments: { status: string; location: string }[];
}
const kindLabels: Record<string, string> = {
  product: "产品身份",
  variant: "具体配置",
  source_link: "来源关联",
  knowledge: "搭配知识",
  question: "待确认问题",
};
export default function ExtractionPage() {
  const client = useQueryClient();
  const { message } = App.useApp();
  const [jobForm] = Form.useForm(),
    [textForm] = Form.useForm(),
    [reviewForm] = Form.useForm();
  const [importId, setImport] = useState<string>(),
    [textOpen, setTextOpen] = useState(false),
    [selected, setSelected] = useState<string[]>([]),
    [decision, setDecision] = useState<"accept" | "reject">(),
    [editing, setEditing] = useState<Draft>();
  const imports = useQuery({
    queryKey: ["imports"],
    queryFn: () => api<CatalogImport[]>("/imports"),
  });
  const sourceImport = importId ?? imports.data?.[0]?.id;
  const sources = useQuery({
    queryKey: ["products", sourceImport],
    enabled: !!sourceImport,
    queryFn: () => api<Product[]>("/products?import_id=" + sourceImport),
  });
  const variants = useVariants();
  const products = useProducts();
  const materials = useQuery({
    queryKey: ["configuration", "materials"],
    queryFn: () => api<Material[]>(ROOT + "/extraction/materials"),
  });
  const jobs = useQuery({
    queryKey: ["configuration", "jobs"],
    queryFn: () => api<Job[]>(ROOT + "/extraction/jobs"),
    refetchInterval: (query) =>
      query.state.data?.some((j) => ["queued", "running"].includes(j.status))
        ? 3000
        : false,
  });
  const drafts = useQuery({
    queryKey: [
      "configuration",
      "drafts",
      jobs.data?.filter((j) => j.status === "completed").length,
    ],
    queryFn: () => api<Draft[]>(ROOT + "/extraction/drafts"),
  });
  const refresh = () =>
    client.invalidateQueries({ queryKey: ["configuration"] });
  const request = useMutation({
    mutationFn: ({ path, body }: { path: string; body: object | FormData }) =>
      api(ROOT + "/extraction/" + path, {
        method: "POST",
        body: body instanceof FormData ? body : JSON.stringify(body),
      }),
    onSuccess: () => {
      refresh();
      message.success("操作已记录");
      setTextOpen(false);
    },
    onError: (e) => message.error(e.message),
  });
  const review = useMutation({
    mutationFn: (values: object) =>
      api(ROOT + "/extraction/decisions", {
        method: "POST",
        body: JSON.stringify({
          ...values,
          draft_ids: selected,
          action: decision,
        }),
      }),
    onSuccess: () => {
      refresh();
      setDecision(undefined);
      setSelected([]);
      message.success("审核已完成");
    },
    onError: (e) => message.error(e.message),
  });
  const error =
    imports.error ||
    sources.error ||
    materials.error ||
    jobs.error ||
    drafts.error;
  return (
    <div className="configuration-page">
      <Typography.Title level={2}>AI 资料整理</Typography.Title>
      <Alert
        type="info"
        showIcon
        title="先提取草稿，再由维护者确认。"
        description="上传不会自动调用模型；启动任务会把所选原文发送到已配置的模型服务。支持 Excel、文字型 PDF 和粘贴说明，不支持扫描件识别。"
      />
      {error ? <Alert type="error" title={error.message} /> : null}
      <Tabs
        items={[
          {
            key: "extract",
            label: "资料与任务",
            children: (
              <>
                <Card title="选择资料并提取">
                  <Form
                    form={jobForm}
                    layout="vertical"
                    initialValues={{
                      source_ids: [],
                      material_ids: [],
                      variant_ids: [],
                    }}
                    onFinish={(values) =>
                      request.mutate({ path: "jobs", body: values })
                    }
                  >
                    <Space wrap>
                      <Select
                        style={{ width: 340 }}
                        value={sourceImport}
                        options={imports.data?.map((i) => ({
                          value: i.id,
                          label: i.filename,
                        }))}
                        onChange={(value) => {
                          setImport(value);
                          jobForm.setFieldValue("source_ids", []);
                        }}
                      />
                      <Button
                        onClick={() =>
                          jobForm.setFieldValue(
                            "source_ids",
                            sources.data?.map((p) => p.id) ?? [],
                          )
                        }
                      >
                        选择全部来源
                      </Button>
                    </Space>
                    <Form.Item name="source_ids" label="Excel 来源范围">
                      <Select
                        mode="multiple"
                        maxTagCount="responsive"
                        showSearch
                        optionFilterProp="label"
                        options={sources.data?.map((p) => ({
                          value: p.id,
                          label: `${p.model} · ${p.sheet} 第${p.row}行`,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name="material_ids" label="文字资料">
                      <Select
                        mode="multiple"
                        options={materials.data?.map((m) => ({
                          value: m.id,
                          label: m.name,
                        }))}
                      />
                    </Form.Item>
                    <Space>
                      <Button onClick={() => setTextOpen(true)}>
                        粘贴产品说明
                      </Button>
                      <Upload
                        accept=".pdf"
                        showUploadList={false}
                        beforeUpload={(file) => {
                          const body = new FormData();
                          body.append("file", file);
                          request.mutate({ path: "materials/pdf", body });
                          return false;
                        }}
                      >
                        <Button>上传文字型 PDF</Button>
                      </Upload>
                    </Space>
                    <Form.Item
                      name="product_ids"
                      label="产品身份范围（新配置归属）"
                    >
                      <Select
                        mode="multiple"
                        showSearch
                        optionFilterProp="label"
                        options={products.data?.map((p) => ({
                          value: p.id,
                          label: p.model + " · " + p.name,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item
                      name="variant_ids"
                      label="已整理配置范围（可选）"
                      extra="自动包含所选 Excel 来源已关联的配置；其余产品资料不会发送给模型。"
                    >
                      <Select
                        mode="multiple"
                        options={variantOptions(variants.data)}
                      />
                    </Form.Item>
                    <AuthorFields />
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={request.isPending}
                    >
                      启动提取任务
                    </Button>
                  </Form>
                </Card>
                <Card title="任务进度" style={{ marginTop: 16 }}>
                  <Table<Job>
                    rowKey="id"
                    dataSource={jobs.data}
                    columns={[
                      { title: "任务", render: (_, j) => j.id.slice(0, 8) },
                      {
                        title: "状态",
                        render: (_, j) => <Status value={j.status} />,
                      },
                      {
                        title: "已处理 / 总段数",
                        render: (_, j) =>
                          `${j.segments.filter((s) => s.status === "completed").length} / ${j.segments.length}`,
                      },
                      { title: "问题", dataIndex: "error" },
                      {
                        title: "操作",
                        render: (_, j) =>
                          ["failed", "interrupted"].includes(j.status) ? (
                            <Button
                              onClick={() =>
                                request.mutate({
                                  path: `jobs/${j.id}/retry`,
                                  body: {},
                                })
                              }
                            >
                              重试未完成段落
                            </Button>
                          ) : null,
                      },
                    ]}
                  />
                </Card>
              </>
            ),
          },
          {
            key: "drafts",
            label: "草稿审核",
            children: (
              <Card>
                <Space style={{ marginBottom: 16 }}>
                  <Button
                    disabled={!selected.length}
                    onClick={() => setDecision("accept")}
                  >
                    接受所选
                  </Button>
                  <Button
                    disabled={!selected.length}
                    onClick={() => setDecision("reject")}
                  >
                    拒绝所选
                  </Button>
                  <Button onClick={() => refresh()}>刷新</Button>
                </Space>
                <Table<Draft>
                  rowKey="id"
                  dataSource={drafts.data}
                  rowSelection={{
                    selectedRowKeys: selected,
                    onChange: (keys) => setSelected(keys as string[]),
                    getCheckboxProps: (d) => ({
                      disabled: d.status !== "pending",
                    }),
                  }}
                  columns={[
                    { title: "类型", render: (_, d) => kindLabels[d.kind] },
                    { title: "来源", dataIndex: "location" },
                    { title: "原文依据", dataIndex: "quotation" },
                    {
                      title: "状态",
                      render: (_, d) => <Status value={d.status} />,
                    },
                    {
                      title: "操作",
                      render: (_, d) => (
                        <Button
                          disabled={d.status !== "pending"}
                          onClick={() => setEditing(d)}
                        >
                          对照原文并编辑
                        </Button>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "settings",
            label: "模型设置",
            children: (
              <Card>
                <ModelSettings />
              </Card>
            ),
          },
        ]}
      />
      <Modal
        title="添加文字资料"
        open={textOpen}
        onCancel={() => setTextOpen(false)}
        onOk={() => textForm.submit()}
      >
        <Form
          form={textForm}
          layout="vertical"
          onFinish={(body) => request.mutate({ path: "materials/text", body })}
        >
          <Form.Item name="name" label="资料名称" rules={required}>
            <Input />
          </Form.Item>
          <Form.Item name="text" label="原始说明" rules={required}>
            <Input.TextArea rows={10} />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={decision === "accept" ? "确认接受所选草稿" : "确认拒绝所选草稿"}
        open={!!decision}
        onCancel={() => setDecision(undefined)}
        onOk={() => reviewForm.submit()}
        confirmLoading={review.isPending}
      >
        <Form
          form={reviewForm}
          layout="vertical"
          onFinish={(v) => review.mutate(v)}
        >
          <AuthorFields />
        </Form>
      </Modal>
      {editing ? (
        <DraftReview draft={editing} onClose={() => setEditing(undefined)} />
      ) : null}
    </div>
  );
}
