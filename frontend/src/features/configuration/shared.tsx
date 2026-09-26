import { useQuery } from "@tanstack/react-query";
import {
  AutoComplete,
  Button,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
} from "antd";
import { api } from "../../shared/api";
import type {
  Attribute,
  AttributeDefinition,
  Knowledge,
  Product,
  Variant,
} from "./types";
import { configurationKeys } from "./queryKeys";

export const ROOT = "/configuration";
export const units = [
  "GB",
  "MB",
  "TB",
  "mm",
  "cm",
  "m",
  "W",
  "台",
  "个",
  "路",
  "席",
  "核",
];
export const statusLabels: Record<string, string> = {
  pass: "通过已知检查",
  conflict: "明确冲突",
  unknown: "资料不足",
  draft: "草稿",
  confirmed: "已确认",
  disabled: "停用",
  pending: "待审核",
  blocked: "明确阻塞",
  accept: "已接受",
  reject: "已拒绝",
  queued: "等待处理",
  running: "处理中",
  completed: "提取完成",
  failed: "失败",
  interrupted: "中断",
};
export function Status({ value }: { value: string }) {
  return (
    <Tag
      color={
        ["pass", "confirmed", "completed", "accept"].includes(value)
          ? "green"
          : ["conflict", "failed"].includes(value)
            ? "red"
            : "gold"
      }
    >
      {statusLabels[value] ?? value}
    </Tag>
  );
}
export function useVariants() {
  return useQuery({
    queryKey: configurationKeys.variants,
    queryFn: () => api<Variant[]>(ROOT + "/variants"),
  });
}
export function useProducts() {
  return useQuery({
    queryKey: configurationKeys.products,
    queryFn: () => api<Product[]>(ROOT + "/products"),
  });
}
export function useKnowledge() {
  return useQuery({
    queryKey: configurationKeys.knowledge,
    queryFn: () => api<Knowledge[]>(ROOT + "/knowledge"),
  });
}
export function useAttributeDefinitions() {
  return useQuery({
    queryKey: configurationKeys.attributeDefinitions,
    queryFn: () =>
      api<AttributeDefinition[]>(ROOT + "/attribute-definitions"),
    staleTime: Infinity,
  });
}
export const variantOptions = (variants: Variant[] | undefined) =>
  variants?.map((v) => ({
    value: v.id,
    label: `${v.product.model} · ${v.name}`,
  }));
export const required = [{ required: true, message: "请填写此项" }];
export function AuthorFields() {
  return (
    <Space align="start" wrap>
      <Form.Item name="actor" label="维护人" rules={required}>
        <Input />
      </Form.Item>
      <Form.Item name="evidence" label="依据 / 确认说明" rules={required}>
        <Input.TextArea autoSize placeholder="资料出处或本次确认的说明" />
      </Form.Item>
    </Space>
  );
}
export function AttributeEditor({ name = "attributes" }: { name?: string }) {
  const form = Form.useFormInstance();
  const definitions = useAttributeDefinitions();
  const values = Form.useWatch(name, form) as Attribute[] | undefined;
  return (
    <Form.List name={name}>
      {(fields, { add, remove }) => (
        <Space orientation="vertical" style={{ width: "100%" }}>
          {fields.map((field) => (
            <div className="config-field-row" key={field.key}>
              <Form.Item
                name={[field.name, "key"]}
                label="参数"
                rules={required}
                help={
                  values?.[field.name]?.key &&
                  !definitions.data?.some(
                    (item) => item.key === values[field.name].key,
                  )
                    ? "未注册字段：会保留原值，但规则只能按完全相同的键匹配"
                    : undefined
                }
                validateStatus={
                  values?.[field.name]?.key &&
                  !definitions.data?.some(
                    (item) => item.key === values[field.name].key,
                  )
                    ? "warning"
                    : undefined
                }
              >
                <AutoComplete
                  options={definitions.data?.flatMap((item) => [
                    { value: item.key, label: item.label },
                    ...item.aliases.map((alias) => ({
                      value: alias,
                      label: `${item.label}（旧字段 ${alias}）`,
                    })),
                  ])}
                />
              </Form.Item>
              <Form.Item name={[field.name, "kind"]} label="类型">
                <Select
                  options={[
                    { value: "text", label: "文字" },
                    { value: "enum", label: "多个值" },
                    { value: "number", label: "数值" },
                    { value: "quantity", label: "带单位数值" },
                  ]}
                  onChange={() =>
                    form.setFieldValue([name, field.name, "value"], null)
                  }
                />
              </Form.Item>
              <Form.Item
                name={[field.name, "value"]}
                label="值（留空表示未知）"
              >
                {values?.[field.name]?.kind === "enum" ? (
                  <Select mode="tags" />
                ) : values?.[field.name]?.kind === "number" ||
                  values?.[field.name]?.kind === "quantity" ? (
                  <InputNumber stringMode style={{ width: "100%" }} />
                ) : (
                  <Input />
                )}
              </Form.Item>
              <Form.Item name={[field.name, "unit"]} label="单位">
                <Select
                  allowClear
                  options={units.map((value) => ({ value, label: value }))}
                />
              </Form.Item>
              <Button danger onClick={() => remove(field.name)}>
                移除
              </Button>
            </div>
          ))}
          <Button
            onClick={() =>
              add({ key: "", kind: "text", value: null, unit: "" })
            }
          >
            添加参数
          </Button>
        </Space>
      )}
    </Form.List>
  );
}
export function cleanAttributes(values: Attribute[] = []) {
  return values.map((a) => ({
    ...a,
    unit: a.kind === "quantity" ? a.unit || "" : "",
    value:
      a.value === "" || (Array.isArray(a.value) && a.value.length === 0)
        ? null
        : a.value ?? null,
  }));
}

export function sourceOptions(variant: Variant | undefined) {
  return variant?.source_ids.map((id) => {
    const source = variant.source_details?.find((s) => s.id === id);
    return {
      value: id,
      label: source
        ? `${source.sheet} · 第 ${source.row} 行 · ${source.import_id.slice(0, 8)}`
        : id,
    };
  });
}
