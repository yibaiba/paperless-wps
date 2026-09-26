import { Alert, Collapse, Form, Input, InputNumber, Select, Space } from "antd";
import type { Knowledge } from "../types";
import { ConditionsEditor } from "../KnowledgeEditor";
import { required } from "../shared";
import { KnowledgeSentence } from "./KnowledgeSentence";

export function KnowledgeRuleStep({
  kind,
  quantitySource,
  summary,
}: {
  kind?: Knowledge["kind"];
  quantitySource?: Knowledge["quantity_source"];
  summary: string;
}) {
  return (
    <>
      <KnowledgeSentence summary={summary} />
      {kind === "accessory" ? (
        <>
          <Alert
            type="info"
            showIcon
            title="默认按 1:1 配套"
            description="每个所选产品增加 1 个配套。数量关系不同时再展开修改。"
            style={{ marginBottom: 16 }}
          />
          <Collapse
            items={[
              {
                key: "quantity",
                label: "数量不是 1:1，修改计算方式",
                children: (
                  <AccessoryCalculationFields quantitySource={quantitySource} />
                ),
              },
              {
                key: "output",
                label: "清单分类与已有设备抵扣方式",
                children: <AccessoryOutputFields />,
              },
            ]}
          />
        </>
      ) : null}
      <Collapse
        style={{ marginTop: 16 }}
        items={[
          {
            key: "conditions",
            label: "有操作系统、CPU、容量等限制条件时添加",
            children: <ConditionsEditor />,
          },
        ]}
      />
    </>
  );
}

function AccessoryCalculationFields({
  quantitySource,
}: {
  quantitySource?: Knowledge["quantity_source"];
}) {
  return (
    <>
      <Space wrap align="start">
        <Form.Item name="calculation_scope" label="按什么范围计算">
          <Select
            style={{ width: 190 }}
            options={[
              { value: "device", label: "每个部署设备" },
              { value: "system", label: "每个系统实例" },
              { value: "room", label: "每个房间" },
              { value: "project", label: "整个项目" },
            ]}
          />
        </Form.Item>
        <Form.Item name="quantity_source" label="依据什么数量">
          <Select
            style={{ width: 190 }}
            options={[
              { value: "device_quantity", label: "范围内设备数量" },
              { value: "environment", label: "需求中的数值参数" },
            ]}
          />
        </Form.Item>
        {quantitySource === "environment" ? (
          <Form.Item name="quantity_key" label="需求参数" rules={required}>
            <Select
              style={{ width: 180 }}
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
        <Form.Item name="mode" label="计算方式">
          <Select
            style={{ width: 190 }}
            options={[
              { value: "per_unit", label: "数量乘系数" },
              { value: "per_capacity", label: "按容量向上取整" },
              { value: "per_group", label: "范围内固定数量" },
            ]}
          />
        </Form.Item>
        <Form.Item name="factor" label="系数 / 容量 / 固定数量" rules={required}>
          <InputNumber stringMode min="0.000001" />
        </Form.Item>
        <Form.Item name="need_key" label="需求标识（可选）">
          <Input placeholder="例如：server" />
        </Form.Item>
      </Space>
    </>
  );
}

function AccessoryOutputFields() {
  return (
    <Space wrap align="start">
      <Form.Item name="output_kind" label="放入哪类清单">
        <Select
          style={{ width: 160 }}
          options={[
            { value: "hardware", label: "硬件" },
            { value: "software", label: "软件" },
            { value: "license", label: "授权" },
            { value: "accessory", label: "配件" },
          ]}
        />
      </Form.Item>
      <Form.Item name="allocation_mode" label="已有设备如何抵扣">
        <Select
          style={{ width: 220 }}
          options={[
            { value: "consumable", label: "数量不能重复占用" },
            { value: "shareable", label: "有依据时可以共享" },
          ]}
        />
      </Form.Item>
    </Space>
  );
}
