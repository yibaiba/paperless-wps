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
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { api } from "../../shared/api";
import type { CatalogImport, Product as Source } from "../../shared/types";
import { ProductDrawer } from "../catalog/ProductDrawer";
import type { Product, Variant } from "./types";
import {
  AuthorFields,
  ROOT,
  Status,
  useProducts,
  useVariants,
  variantOptions,
} from "./shared";
import { ProductEditor, VariantEditor } from "./CatalogEditor";
import "./configuration.css";
import { IndependentSources } from "./IndependentSources";
interface Row extends Source {
  organized: boolean;
  duplicate_model: boolean;
  link_revision: number;
  variant_id: string | null;
  variant: Variant | null;
}
interface Audit {
  rows: Row[];
  total: number;
  organized: number;
  pending: number;
  conflicts: number;
}
export default function CatalogOrganizePage() {
  const [independent, setIndependent] = useState(false);
  const [sourceHistory, setSourceHistory] = useState<string>();
  const imports = useQuery({
    queryKey: ["imports"],
    queryFn: () => api<CatalogImport[]>("/imports"),
  });
  const [importId, setImport] = useState<string>();
  const selectedImport = importId ?? imports.data?.[0]?.id;
  const audit = useQuery({
    queryKey: ["configuration", "audit", selectedImport],
    enabled: !!selectedImport,
    queryFn: () => api<Audit>(ROOT + "/audit/" + selectedImport),
  });
  const products = useProducts(),
    variants = useVariants();
  const client = useQueryClient();
  const { message } = App.useApp();
  const [selected, setSelected] = useState<string[]>([]),
    [search, setSearch] = useState(""),
    [pending, setPending] = useState(false);
  const [product, setProduct] = useState<Product | null>(),
    [variant, setVariant] = useState<Variant | null>();
  const [linking, setLinking] = useState(false),
    [detail, setDetail] = useState<string>(),
    [history, setHistory] = useState<string>();
  const [form] = Form.useForm();
  const revisions = useQuery({
    queryKey: ["configuration", "history", history, sourceHistory],
    enabled: !!history || !!sourceHistory,
    queryFn: () =>
      api<Record<string, unknown>[]>(
        ROOT +
          (sourceHistory
            ? "/source-history/" + sourceHistory
            : "/history/" + history),
      ),
  });
  const link = useMutation({
    mutationFn: (values: object) =>
      api(ROOT + "/source-links", {
        method: "POST",
        body: JSON.stringify({
          ...values,
          items: selected.map((id) => ({
            source_id: id,
            expected_revision: audit.data!.rows.find((r) => r.id === id)!
              .link_revision,
          })),
        }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["configuration"] });
      setLinking(false);
      setSelected([]);
      message.success("来源归属已记录，原资料保持不变");
    },
    onError: (e) => message.error(e.message),
  });
  const error =
    imports.error || audit.error || products.error || variants.error;
  const rows = audit.data?.rows.filter(
    (r) =>
      (!pending || !r.organized) &&
      `${r.model} ${r.name} ${r.sheet}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <div className="configuration-page">
      <Typography.Title level={2}>产品整理</Typography.Title>
      <Alert
        type="info"
        showIcon
        title="先整理产品身份与具体配置，再确认资料来源；型号相同不自动合并。"
        description="配置整理完成不代表搭配已验证。缺少的参数可以明确留空。"
      />
      {error ? <Alert type="error" title={error.message} /> : null}
      <Space wrap>
        <Select
          value={selectedImport}
          style={{ minWidth: 300 }}
          options={imports.data?.map((i) => ({
            value: i.id,
            label: i.filename,
          }))}
          onChange={(v) => {
            setImport(v);
            setSelected([]);
          }}
        />
        <Button onClick={() => setProduct(null)}>建立产品</Button>
        <Button onClick={() => setVariant(null)}>建立配置</Button>
      </Space>
      <Card>
        <Space wrap size={32}>
          <Statistic title="全部来源" value={audit.data?.total ?? 0} />
          <Statistic title="已确认归属" value={audit.data?.organized ?? 0} />
          <Statistic title="未完成" value={audit.data?.pending ?? 0} />
          <Statistic title="涉及资料问题" value={audit.data?.conflicts ?? 0} />
        </Space>
      </Card>
      <Tabs
        items={[
          {
            key: "sources",
            label: "全量来源核对",
            children: (
              <Card>
                <Space wrap style={{ marginBottom: 16 }}>
                  <Input.Search
                    placeholder="型号、名称、工作表"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                  <Button
                    type={pending ? "primary" : "default"}
                    onClick={() => setPending(!pending)}
                  >
                    只看未完成
                  </Button>
                  <Button
                    disabled={!selected.length}
                    onClick={() => setLinking(true)}
                  >
                    关联所选 {selected.length} 条来源
                  </Button>
                  <Button
                    disabled={!selected.length}
                    onClick={() => setIndependent(true)}
                  >
                    分别确认为独立配置
                  </Button>
                  <Button
                    onClick={() =>
                      setSelected(
                        audit.data?.rows
                          .filter((r) => !r.organized)
                          .map((r) => r.id) ?? [],
                      )
                    }
                  >
                    选择全部未整理
                  </Button>
                </Space>
                <Table<Row>
                  rowKey="id"
                  dataSource={rows}
                  loading={audit.isLoading}
                  scroll={{ x: 1050 }}
                  rowSelection={{
                    selectedRowKeys: selected,
                    preserveSelectedRowKeys: true,
                    onChange: (keys) => setSelected(keys as string[]),
                  }}
                  columns={[
                    {
                      title: "产品",
                      render: (_, r) => (
                        <>
                          <strong>{r.model}</strong>
                          <div>{r.name}</div>
                          {r.duplicate_model ? (
                            <Tag>同型号多来源，需核对</Tag>
                          ) : null}
                        </>
                      ),
                    },
                    {
                      title: "原始来源",
                      render: (_, r) => `${r.sheet} · 第 ${r.row} 行`,
                    },
                    {
                      title: "归属配置",
                      render: (_, r) =>
                        r.variant
                          ? `${r.variant.product.model} / ${r.variant.name}`
                          : "未整理",
                    },
                    {
                      title: "状态",
                      render: (_, r) => (
                        <Status value={r.organized ? "confirmed" : "pending"} />
                      ),
                    },
                    {
                      title: "资料问题",
                      render: (_, r) => r.review_summary.total,
                    },
                    {
                      title: "操作",
                      render: (_, r) => (
                        <Button onClick={() => setDetail(r.id)}>
                          查看原文
                        </Button>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "products",
            label: "产品身份",
            children: (
              <Table<Product>
                rowKey="id"
                dataSource={products.data}
                columns={[
                  { title: "型号", dataIndex: "model" },
                  { title: "名称", dataIndex: "name" },
                  { title: "类别", dataIndex: "category" },
                  {
                    title: "操作",
                    render: (_, p) => (
                      <Space>
                        <Button onClick={() => setProduct(p)}>编辑</Button>
                        <Button onClick={() => setHistory(p.id)}>历史</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "variants",
            label: "具体配置",
            children: (
              <Table<Variant>
                rowKey="id"
                dataSource={variants.data}
                columns={[
                  { title: "产品", render: (_, v) => v.product.model },
                  { title: "配置", dataIndex: "name" },
                  { title: "来源数", render: (_, v) => v.source_ids.length },
                  {
                    title: "跨来源差异",
                    render: (_, v) =>
                      v.source_differences
                        ?.map(
                          (f) =>
                            ({
                              specification: "参数",
                              prices: "价格",
                              note: "备注",
                            })[f] ?? f,
                        )
                        .join("、") || "无已发现差异",
                  },
                  {
                    title: "状态",
                    render: (_, v) => <Status value={v.status} />,
                  },
                  {
                    title: "操作",
                    render: (_, v) => (
                      <Space>
                        <Button onClick={() => setVariant(v)}>编辑</Button>
                        <Button onClick={() => setHistory(v.id)}>历史</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
        ]}
      />
      {product !== undefined ? (
        <ProductEditor
          product={product ?? undefined}
          onClose={() => setProduct(undefined)}
        />
      ) : null}
      {variant !== undefined ? (
        <VariantEditor
          variant={variant ?? undefined}
          onClose={() => setVariant(undefined)}
        />
      ) : null}
      <Modal
        title="确认所选来源属于同一具体配置"
        open={linking}
        onCancel={() => setLinking(false)}
        onOk={() => form.submit()}
        confirmLoading={link.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => link.mutate(values)}
        >
          <Form.Item
            name="variant_id"
            label="已确认配置"
            rules={[{ required: true }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={variantOptions(
                variants.data?.filter((v) => v.status === "confirmed"),
              )}
            />
          </Form.Item>
          <AuthorFields />
        </Form>
      </Modal>
      <Modal
        title="修订记录"
        open={!!history || !!sourceHistory}
        onCancel={() => {
          setHistory(undefined);
          setSourceHistory(undefined);
        }}
        footer={null}
      >
        <Table
          rowKey="revision"
          dataSource={revisions.data}
          columns={[
            { title: "版本", dataIndex: "revision" },
            {
              title: "关联配置",
              render: (_, r) =>
                r.variant_id
                  ? (variants.data?.find((v) => v.id === r.variant_id)?.name ??
                    String(r.variant_id))
                  : "—",
            },
            { title: "维护人", dataIndex: "actor" },
            { title: "依据", dataIndex: "evidence" },
          ]}
        />
      </Modal>
      {independent ? (
        <IndependentSources
          sources={
            audit.data?.rows.filter((r) => selected.includes(r.id)) ?? []
          }
          onClose={() => {
            setIndependent(false);
            setSelected([]);
          }}
        />
      ) : null}
      <ProductDrawer id={detail} onClose={() => setDetail(undefined)} />
    </div>
  );
}
