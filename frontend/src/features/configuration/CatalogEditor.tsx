import { App, Form, Input, Modal, Select, Space } from "antd";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../shared/api";
import type { Product, Variant } from "./types";
import {
  AttributeEditor,
  AuthorFields,
  cleanAttributes,
  required,
  ROOT,
  useProducts,
} from "./shared";

import { IncludedItemsEditor } from "./catalog/IncludedItemsEditor";
import { useDefinitions } from "./knowledge/useDefinitions";

export function ProductEditor({
  product,
  onClose,
}: {
  product?: Product;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const client = useQueryClient();
  const { message } = App.useApp();
  const mutation = useMutation({
    mutationFn: (values: object) =>
      api(ROOT + "/products" + (product ? "/" + product.id : ""), {
        method: product ? "PUT" : "POST",
        body: JSON.stringify(
          product
            ? { expected_revision: product.revision, payload: values }
            : values,
        ),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["configuration"] });
      onClose();
    },
    onError: (e) => message.error(e.message),
  });
  return (
    <Modal
      open
      title={product ? "编辑产品身份" : "建立产品身份"}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={mutation.isPending}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={product ?? { brand: "", category: "" }}
        onFinish={(values) => mutation.mutate(values)}
      >
        <Form.Item name="model" label="型号" rules={required}>
          <Input />
        </Form.Item>
        <Form.Item name="name" label="产品名称" rules={required}>
          <Input />
        </Form.Item>
        <Form.Item name="brand" label="品牌">
          <Input />
        </Form.Item>
        <Form.Item name="category" label="类别">
          <Input placeholder="服务器、软件、终端…" />
        </Form.Item>
        <AuthorFields />
      </Form>
    </Modal>
  );
}
export function VariantEditor({
  variant,
  onClose,
}: {
  variant?: Variant;
  onClose: () => void;
}) {
  const [form] = Form.useForm();
  const products = useProducts();
  const definitions = useDefinitions();
  const client = useQueryClient();
  const { message } = App.useApp();
  const mutation = useMutation({
    mutationFn: (values: Variant) =>
      api(ROOT + "/variants" + (variant ? "/" + variant.id : ""), {
        method: variant ? "PUT" : "POST",
        body: JSON.stringify(
          variant
            ? { expected_revision: variant.revision, payload: values }
            : values,
        ),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["configuration"] });
      onClose();
    },
    onError: (e) => message.error(e.message),
  });
  const initial = variant ?? {
    status: "draft",
    attributes: [],
    series: [],
    functions: [],
    interfaces: [],
    systems: [],
  };
  return (
    <Modal
      open
      width={900}
      title={variant ? "编辑具体配置" : "建立具体配置"}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={mutation.isPending}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={initial}
        onFinish={(values) =>
          mutation.mutate({
            ...values,
            attributes: cleanAttributes(values.attributes),
          })
        }
      >
        <Space wrap align="start">
          <Form.Item name="product_id" label="产品" rules={required}>
            <Select
              style={{ width: 260 }}
              showSearch
              optionFilterProp="label"
              options={products.data?.map((p) => ({
                value: p.id,
                label: `${p.model} · ${p.name}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="name" label="配置名称" rules={required}>
            <Input placeholder="例如：64GB / 指定 CPU 配置" />
          </Form.Item>
          <Form.Item name="status" label="整理状态">
            <Select
              options={[
                { value: "draft", label: "草稿" },
                { value: "confirmed", label: "已确认配置" },
              ]}
            />
          </Form.Item>
        </Space>
        <Form.Item name="capability_ids" label="已核对的产品能力"><Select mode="multiple" options={definitions.data?.capabilities.map((c) => ({ value: c.id, label: c.name }))} /></Form.Item>
        <AttributeEditor />
        <Space wrap>
          {[
            ["series", "系列"],
            ["functions", "功能"],
            ["interfaces", "接口"],
            ["systems", "适用系统标签"],
          ].map(([key, label]) => (
            <Form.Item key={key} name={key} label={label}>
              <Select mode="tags" style={{ minWidth: 170 }} />
            </Form.Item>
          ))}
        </Space>
        <IncludedItemsEditor hostId={variant?.id} />
        <AuthorFields />
      </Form>
    </Modal>
  );
}
