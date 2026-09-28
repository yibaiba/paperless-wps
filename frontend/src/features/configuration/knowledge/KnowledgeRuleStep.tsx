import { Alert, Button, Collapse, Form, Input, InputNumber, Select, Space } from "antd";
import type { Knowledge } from "../types";
import { ConditionsEditor } from "./ConditionsEditor";
import { required, units } from "../shared";
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
  const form = Form.useFormInstance();
  return (
    <>
      <KnowledgeSentence summary={summary} />
      {kind === "accessory" ? (
        <>
          <Alert
            type="info"
            showIcon
            title="数量依据与关系分别确认"
            description="可以先记录需要什么配套；数量未确认时只显示待办，不生成补料量。"
            style={{ marginBottom: 16 }}
          />
          <Space wrap style={{ marginBottom: 16 }}>
            <Button onClick={() => form.setFieldsValue({ calculation_scope: "device", mode: "per_unit", factor: "1" })}>明确每台一个</Button>
            <Button onClick={() => form.setFieldsValue({ calculation_scope: "system", mode: "per_group", factor: "1" })}>明确每系统一个</Button>
            <Button onClick={() => form.setFieldsValue({ calculation_scope: null, mode: null, factor: null, quantity_review: "unreviewed" })}>数量待确认</Button>
          </Space>
          <AccessoryCalculationFields quantitySource={quantitySource} />
          <Form.Item name="quantity_review" label="数量依据状态"><Select options={[
            { value: "unreviewed", label: "待确认" }, { value: "confirmed", label: "已核对数量依据" },
          ]} /></Form.Item>
          <Form.Item name="quantity_evidence" label="数量依据"><Input.TextArea placeholder="说明数量口径来自哪项参数或维护者结论" /></Form.Item>
          <Form.Item name="resource_policy" label="配套资源是否需要核算"><Select options={[
            { value: "unknown", label: "待确认" }, { value: "required", label: "需要核算容量" },
            { value: "not_applicable", label: "有依据确认不涉及资源容量" },
          ]} /></Form.Item>
          <Collapse
            items={[
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
      {quantitySource === "environment" ? <Form.Item name="quantity_unit" label="数量输入单位" extra="必须与需求参数单位一致；无单位数值请选择不带单位。">
        <Select options={[{ value: "", label: "不带单位" }, ...units.map((unit) => ({ value: unit, label: unit }))]} />
      </Form.Item> : null}
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
        <Form.Item name="factor" label="系数 / 容量 / 固定数量">
          <InputNumber stringMode />
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
