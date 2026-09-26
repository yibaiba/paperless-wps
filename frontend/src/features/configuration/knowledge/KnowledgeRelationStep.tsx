import { Alert, Form, Input, Select, Space, Typography } from "antd";
import type { Knowledge, Variant } from "../types";
import { SystemTypeInput } from "../SystemTypeInput";
import { required, variantOptions } from "../shared";

export function KnowledgeRelationStep({
  kind,
  variants,
}: {
  kind?: Knowledge["kind"];
  variants?: Variant[];
}) {
  const form = Form.useFormInstance();
  const status = Form.useWatch("status", form) as Knowledge["status"];
  return (
    <>
      <Typography.Title level={5}>这条知识要表达什么？</Typography.Title>
      <Form.Item name="kind" label="关系类型" rules={required}>
        <Select
          options={[
            { value: "suitability", label: "某产品可以用于某个系统角色" },
            { value: "accessory", label: "选择某产品后还需要搭配其他产品" },
            { value: "sharing", label: "一台设备可以给多个系统共同使用" },
          ]}
        />
      </Form.Item>
      <Form.Item
        name={["selector", "variant_ids"]}
        label="哪些产品 / 具体配置适用这条知识"
        rules={[{ type: "array", min: 1, message: "请至少选择一个具体配置" }]}
      >
        <Select
          mode="multiple"
          showSearch
          optionFilterProp="label"
          options={variantOptions(variants)}
          placeholder="可同时选择已经确认相同结论的配置"
        />
      </Form.Item>
      {kind === "suitability" ? <SuitabilityFields /> : null}
      {kind === "accessory" ? (
        <AccessoryFields variants={variants} confirmed={status === "confirmed"} />
      ) : null}
      {kind === "sharing" ? <SharingFields /> : null}
    </>
  );
}

function SuitabilityFields() {
  return (
    <Space wrap align="start" size="middle">
      <Form.Item name="system" label="用于哪个系统 / 方案版本" rules={required}>
        <SystemTypeInput />
      </Form.Item>
      <Form.Item name="role" label="承担什么角色" rules={required}>
        <Input placeholder="例如：服务端软件、会议终端、服务器" />
      </Form.Item>
      <Form.Item name="effect" label="结论">
        <Select
          style={{ width: 220 }}
          options={[
            { value: "allow", label: "可以使用" },
            { value: "deny", label: "明确不能使用" },
          ]}
        />
      </Form.Item>
    </Space>
  );
}

function AccessoryFields({
  variants,
  confirmed,
}: {
  variants?: Variant[];
  confirmed: boolean;
}) {
  return (
    <>
      <Space wrap align="start" size="middle">
        <Form.Item name="need_name" label="还需要什么" rules={required}>
          <Input placeholder="例如：服务器、会议主机、话筒模块" />
        </Form.Item>
        <Form.Item name="accessory_type" label="配套性质">
          <Select
            style={{ width: 180 }}
            options={[
              { value: "required", label: "必需" },
              { value: "recommended", label: "推荐" },
              { value: "optional", label: "可选" },
            ]}
          />
        </Form.Item>
      </Space>
      <Form.Item
        name="target_variant_ids"
        label="可以选择哪些具体配套产品"
        extra="暂时不知道型号时可以留空并保存为草稿。"
        rules={
          confirmed
            ? [{ type: "array", min: 1, message: "已确认知识必须选择配套产品" }]
            : []
        }
      >
        <Select
          mode="multiple"
          showSearch
          optionFilterProp="label"
          options={variantOptions(variants)}
          placeholder="选择一个或多个可以替代的配置"
        />
      </Form.Item>
    </>
  );
}

function SharingFields() {
  return (
    <>
      <Alert
        type="warning"
        showIcon
        title="共享知识必须有明确资料或维护者确认依据"
        description="产品分别适用于两个系统，不代表它们可以共用同一台设备。"
        style={{ marginBottom: 16 }}
      />
      <Form.Item
        name="shared_roles"
        label="允许共同使用这台设备的系统 / 角色"
        rules={[{ type: "array", min: 2, message: "至少填写两个系统 / 角色" }]}
      >
        <Select
          mode="tags"
          tokenSeparators={[",", "，"]}
          placeholder="例如：红盾无纸化/服务端、会议预约/服务端"
        />
      </Form.Item>
      <Form.Item name="effect" label="结论">
        <Select
          options={[
            { value: "allow", label: "满足条件时允许共用" },
            { value: "deny", label: "明确禁止共用" },
          ]}
        />
      </Form.Item>
    </>
  );
}
