import { AutoComplete, Button, Form, Input, InputNumber, Select, Space } from "antd";
import type { Knowledge } from "../types";
import { required, units, useAttributeDefinitions } from "../shared";

export function ConditionsEditor({ name = "conditions", path }: { name?: string | (string | number)[]; path?: (string | number)[] }) {
  const fullPath = path ?? (Array.isArray(name) ? name : [name]);
  const form = Form.useFormInstance();
  const definitions = useAttributeDefinitions();
  const conditions = Form.useWatch(fullPath, form) as
    Knowledge["conditions"] | undefined;
  return (
    <Form.List name={name}>
      {(fields, { add, remove }) => (
        <Space orientation="vertical" style={{ width: "100%" }}>
          {fields.map((field) => (
            <div className="config-field-row" key={field.key}>
              <Form.Item
                name={[field.name, "field"]}
                label="条件字段"
                help={conditions?.[field.name]?.field && !definitions.data?.some((d) => [`product.${d.key}`, `project.${d.key}`].includes(conditions[field.name].field)) ? "未注册字段：保留原键名，需确认与实际参数一致" : undefined}
                rules={required}
              >
                <AutoComplete
                  placeholder="选择条件字段"
                  options={definitions.data?.flatMap((d) => [
                    { value: `product.${d.key}`, label: `产品 ${d.label}` },
                    { value: `project.${d.key}`, label: `需求 ${d.label}` },
                  ])}
                />
              </Form.Item>
              <Form.Item name={[field.name, "operator"]} label="比较方式">
                <Select
                  options={[
                    { value: "eq", label: "等于" },
                    { value: "any", label: "任一匹配" },
                    { value: "all", label: "全部匹配" },
                    { value: "range", label: "范围" },
                  ]}
                  onChange={() =>
                    form.setFieldValue(
                      [...fullPath, field.name, "value"],
                      null,
                    )
                  }
                />
              </Form.Item>
              {conditions?.[field.name]?.operator === "range" ? (
                <Space>
                  <Form.Item name={[field.name, "minimum"]} label="下限">
                    <InputNumber stringMode />
                  </Form.Item>
                  <Form.Item name={[field.name, "maximum"]} label="上限">
                    <InputNumber stringMode />
                  </Form.Item>
                </Space>
              ) : (
                <Form.Item name={[field.name, "value"]} label="条件值">
                  {["any", "all"].includes(
                    conditions?.[field.name]?.operator ?? "",
                  ) ? (
                    <Select mode="tags" />
                  ) : (
                    <Input />
                  )}
                </Form.Item>
              )}
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
              add({
                field: "",
                operator: "eq",
                value: null,
                minimum: null,
                maximum: null,
                unit: "",
              })
            }
          >
            添加条件
          </Button>
        </Space>
      )}
    </Form.List>
  );
}
