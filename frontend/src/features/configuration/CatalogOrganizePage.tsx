import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Form, Select, Space, Tabs, Typography } from "antd";
import { api } from "../../shared/api";
import type { CatalogImport } from "../../shared/types";
import { ProductDrawer } from "../catalog/ProductDrawer";
import type { Product, Variant } from "./types";
import { ROOT, useProducts, useVariants } from "./shared";
import { ProductEditor, VariantEditor } from "./CatalogEditor";
import "./configuration.css";
import { IndependentSources } from "./IndependentSources";
import { SearchIndexPanel } from "./SearchIndexPanel";
import { SourceBlockModal } from "./SourceBlockModal";
import { configurationKeys } from "./queryKeys";
import { suggestedEvidence } from "./SourceMatchSuggestions";
import {
  CatalogProductsTable,
  CatalogVariantsTable,
} from "./catalog/CatalogEntityTables";
import { CatalogHistoryModal, SourceLinkModal } from "./catalog/CatalogModals";
import {
  CatalogAuditSummary,
  CatalogSourceAuditPanel,
} from "./catalog/CatalogSourceAuditPanel";
import type {
  CatalogAudit,
  CatalogAuditRow,
  CatalogAuditStatus,
} from "./catalog/types";

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
    queryKey: configurationKeys.audit(selectedImport),
    enabled: !!selectedImport,
    queryFn: () => api<CatalogAudit>(ROOT + "/audit/" + selectedImport),
  });
  const products = useProducts();
  const variants = useVariants();
  const client = useQueryClient();
  const { message } = App.useApp();
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<CatalogAuditStatus>("all");
  const [product, setProduct] = useState<Product | null>();
  const [variant, setVariant] = useState<Variant | null>();
  const [linking, setLinking] = useState(false);
  const [blocking, setBlocking] = useState(false);
  const [detail, setDetail] = useState<string>();
  const [history, setHistory] = useState<string>();
  const [form] = Form.useForm();
  const revisions = useSourceHistory(history, sourceHistory);
  const link = useMutation({
    mutationFn: (values: object) =>
      api(ROOT + "/source-links", {
        method: "POST",
        body: JSON.stringify({
          ...values,
          items: selected.map((id) => ({
            source_id: id,
            expected_revision: audit.data!.rows.find((row) => row.id === id)!
              .link_revision,
          })),
        }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: configurationKeys.all });
      setLinking(false);
      setSelected([]);
      form.resetFields();
      message.success("来源归属已记录，原资料保持不变");
    },
    onError: (error) => message.error(error.message),
  });
  const error = imports.error || audit.error || products.error || variants.error;
  const rows = filteredRows(audit.data?.rows, status, search);
  const closeHistory = () => {
    setHistory(undefined);
    setSourceHistory(undefined);
  };

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
          options={imports.data?.map((item) => ({ value: item.id, label: item.filename }))}
          onChange={(value) => {
            setImport(value);
            setSelected([]);
          }}
        />
        <Button onClick={() => setProduct(null)}>建立产品</Button>
        <Button onClick={() => setVariant(null)}>建立配置</Button>
      </Space>
      <CatalogAuditSummary audit={audit.data} />
      <Tabs
        items={[
          {
            key: "sources",
            label: "全量来源核对",
            children: (
              <CatalogSourceAuditPanel
                rows={rows}
                loading={audit.isLoading}
                selected={selected}
                search={search}
                status={status}
                onSelected={setSelected}
                onSearch={setSearch}
                onStatus={setStatus}
                onLinkSelected={() => {
                  form.resetFields();
                  setLinking(true);
                }}
                onIndependentSelected={() => setIndependent(true)}
                onBlockSelected={() => setBlocking(true)}
                onSelectPending={() =>
                  setSelected(
                    audit.data?.rows
                      .filter((row) => !row.organized && !row.blocked)
                      .map((row) => row.id) ?? [],
                  )
                }
                onSuggestedLink={(row, suggestion) => {
                  setSelected([row.id]);
                  form.setFieldsValue({
                    variant_id: suggestion.variant_id,
                    actor: "",
                    evidence: suggestedEvidence(suggestion),
                  });
                  setLinking(true);
                }}
                onDetail={setDetail}
                onHistory={setSourceHistory}
              />
            ),
          },
          {
            key: "products",
            label: "产品身份",
            children: (
              <CatalogProductsTable
                products={products.data}
                onEdit={setProduct}
                onHistory={setHistory}
              />
            ),
          },
          { key: "search-index", label: "智能索引", children: <SearchIndexPanel /> },
          {
            key: "variants",
            label: "具体配置",
            children: (
              <CatalogVariantsTable
                variants={variants.data}
                onEdit={setVariant}
                onHistory={setHistory}
              />
            ),
          },
        ]}
      />
      {product !== undefined ? (
        <ProductEditor product={product ?? undefined} onClose={() => setProduct(undefined)} />
      ) : null}
      {variant !== undefined ? (
        <VariantEditor variant={variant ?? undefined} onClose={() => setVariant(undefined)} />
      ) : null}
      <SourceLinkModal
        open={linking}
        selectedCount={selected.length}
        variants={variants.data}
        form={form}
        loading={link.isPending}
        onCancel={() => setLinking(false)}
        onSubmit={(values) => link.mutate(values)}
      />
      <CatalogHistoryModal
        open={!!history || !!sourceHistory}
        rows={revisions.data}
        variants={variants.data}
        onClose={closeHistory}
      />
      {independent ? (
        <IndependentSources
          sources={audit.data?.rows.filter((row) => selected.includes(row.id)) ?? []}
          onClose={() => {
            setIndependent(false);
            setSelected([]);
          }}
        />
      ) : null}
      {blocking ? (
        <SourceBlockModal
          sources={audit.data?.rows.filter((row) => selected.includes(row.id)) ?? []}
          onClose={() => {
            setBlocking(false);
            setSelected([]);
          }}
        />
      ) : null}
      <ProductDrawer id={detail} onClose={() => setDetail(undefined)} />
    </div>
  );
}

function useSourceHistory(history?: string, sourceHistory?: string) {
  return useQuery({
    queryKey: [
      ...configurationKeys.history(history ?? sourceHistory),
      sourceHistory ? "source" : "entity",
    ],
    enabled: !!history || !!sourceHistory,
    queryFn: () =>
      api<Record<string, unknown>[]>(
        ROOT +
          (sourceHistory ? "/source-history/" + sourceHistory : "/history/" + history),
      ),
  });
}

function filteredRows(
  rows: CatalogAuditRow[] | undefined,
  status: CatalogAuditStatus,
  search: string,
) {
  const term = search.toLowerCase();
  return rows?.filter(
    (row) =>
      (status === "all" ||
        (status === "pending" && !row.organized && !row.blocked) ||
        (status === "blocked" && row.blocked)) &&
      `${row.model} ${row.name} ${row.sheet}`.toLowerCase().includes(term),
  );
}
