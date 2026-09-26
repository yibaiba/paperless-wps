import { Button, Space, Table } from "antd";
import type { Product, Variant } from "../types";
import { Status } from "../shared";

export function CatalogProductsTable({
  products,
  onEdit,
  onHistory,
}: {
  products?: Product[];
  onEdit: (product: Product) => void;
  onHistory: (id: string) => void;
}) {
  return (
    <Table<Product>
      rowKey="id"
      dataSource={products}
      columns={[
        { title: "型号", dataIndex: "model" },
        { title: "名称", dataIndex: "name" },
        { title: "类别", dataIndex: "category" },
        {
          title: "操作",
          render: (_, product) => (
            <Space>
              <Button onClick={() => onEdit(product)}>编辑</Button>
              <Button onClick={() => onHistory(product.id)}>历史</Button>
            </Space>
          ),
        },
      ]}
    />
  );
}

export function CatalogVariantsTable({
  variants,
  onEdit,
  onHistory,
}: {
  variants?: Variant[];
  onEdit: (variant: Variant) => void;
  onHistory: (id: string) => void;
}) {
  return (
    <Table<Variant>
      rowKey="id"
      dataSource={variants}
      columns={[
        { title: "产品", render: (_, variant) => variant.product.model },
        { title: "配置", dataIndex: "name" },
        { title: "来源数", render: (_, variant) => variant.source_ids.length },
        {
          title: "跨来源差异",
          render: (_, variant) =>
            variant.source_differences?.map(differenceLabel).join("、") || "无已发现差异",
        },
        { title: "状态", render: (_, variant) => <Status value={variant.status} /> },
        {
          title: "操作",
          render: (_, variant) => (
            <Space>
              <Button onClick={() => onEdit(variant)}>编辑</Button>
              <Button onClick={() => onHistory(variant.id)}>历史</Button>
            </Space>
          ),
        },
      ]}
    />
  );
}

function differenceLabel(value: string) {
  return { specification: "参数", prices: "价格", note: "备注" }[value] ?? value;
}
