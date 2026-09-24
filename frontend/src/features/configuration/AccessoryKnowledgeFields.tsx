import { Form, Input, InputNumber, Select, Space, Typography } from "antd";
import type { Knowledge } from "./types";
import { useVariants, variantOptions } from "./shared";

export function AccessoryKnowledgeFields() {
  const variants = useVariants();
  const form = Form.useFormInstance();
  const quantitySource = Form.useWatch("quantity_source", form) as
    | Knowledge["quantity_source"]
    | undefined;
  return (
    <>
      <Space wrap align="start">
        <Form.Item
          name="need_name"
          label="配套需求名称"
          extra="例如：会议主机、话筒模块。缺少具体型号时也可以先保存草稿。"
        >
          <Input placeholder="会议主机" />
        </Form.Item>
        <Form.Item
          name="need_key"
          label="需求标识（可选）"
          extra="相同需求可使用同一标识，未填写时按本条知识独立计算。"
        >
          <Input placeholder="meeting-host" />
        </Form.Item>
      </Space>
      <Form.Item name="target_variant_ids" label="可选配套配置">
        <Select
          mode="multiple"
          showSearch
          optionFilterProp="label"
          options={variantOptions(variants.data)}
          placeholder="型号未知时留空并保存为草稿"
        />
      </Form.Item>
      <Space wrap align="start">
        <Form.Item name="accessory_type" label="配套性质">
          <Select
            options={[
              { value: "required", label: "必需" },
              { value: "recommended", label: "推荐" },
              { value: "optional", label: "可选" },
            ]}
          />
        </Form.Item>
        <Form.Item name="calculation_scope" label="计算范围">
          <Select
            allowClear
            placeholder="待确认"
            options={[
              { value: "device", label: "每个部署设备" },
              { value: "system", label: "每个系统实例" },
              { value: "room", label: "每个房间" },
              { value: "project", label: "整个项目" },
            ]}
          />
        </Form.Item>
        <Form.Item name="quantity_source" label="数量输入">
          <Select
            options={[
              { value: "device_quantity", label: "范围内设备数量" },
              { value: "environment", label: "需求中的数值参数" },
            ]}
          />
        </Form.Item>
        {quantitySource === "environment" ? (
          <Form.Item name="quantity_key" label="需求参数">
            <Select
              showSearch
              allowClear
              options={[
                { value: "terminal_count", label: "终端数量" },
                { value: "user_count", label: "用户人数" },
                { value: "room_count", label: "房间数量" },
              ]}
            />
          </Form.Item>
        ) : null}
      </Space>
      <Space wrap align="start">
        <Form.Item name="mode" label="数量方式">
          <Select
            allowClear
            placeholder="待确认"
            options={[
              { value: "per_unit", label: "数量乘系数" },
              { value: "per_capacity", label: "按容量向上取整" },
              { value: "per_group", label: "范围内固定数量" },
            ]}
          />
        </Form.Item>
        <Form.Item name="factor" label="系数 / 容量 / 固定数量">
          <InputNumber stringMode min="0" />
        </Form.Item>
        <Form.Item name="output_kind" label="清单类型">
          <Select
            options={[
              { value: "hardware", label: "硬件" },
              { value: "software", label: "软件" },
              { value: "license", label: "授权" },
              { value: "accessory", label: "配件" },
            ]}
          />
        </Form.Item>
        <Form.Item name="allocation_mode" label="已有设备抵扣方式">
          <Select
            options={[
              { value: "consumable", label: "数量不可重复占用" },
              { value: "shareable", label: "有依据时可共享" },
            ]}
          />
        </Form.Item>
      </Space>
      <Typography.Paragraph type="secondary">
        已确认配套必须补齐候选配置、计算范围和数量公式；草稿可以保留缺项。
      </Typography.Paragraph>
    </>
  );
}
