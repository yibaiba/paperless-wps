import { CombinationFields } from "./CombinationFields";
import { Alert, Form, Input, Select, Space, Typography } from "antd";
import type { Knowledge, Variant } from "../types";
import { QuickIdentity } from "./QuickIdentity";
import { SharedRoleSelect } from "./SharedRoleSelect";
import { required, variantOptions } from "../shared";

export function KnowledgeRelationStep({
  kind,
  variants,
}: {
  kind?: Knowledge["kind"];
  variants?: Variant[];
}) {


  return (
    <>
      <Typography.Title level={5}>这条知识要表达什么？</Typography.Title>
      <Form.Item name="kind" label="关系类型" rules={required}>
        <Select
          options={[
            { value: "suitability", label: "某产品可以用于某个系统角色" },
            { value: "accessory", label: "选择某产品后还需要搭配其他产品" },
            { value: "sharing", label: "一台设备可以给多个系统共同使用" },
            { value: "combination", label: "产品之间的互斥或必选组合" },
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
        <AccessoryFields variants={variants} />
      ) : null}
      {kind === "sharing" ? <SharingFields /> : null}
      {kind === "combination" ? <CombinationFields variants={variants} /> : null}
    </>
  );
}

function SuitabilityFields() {
  return (
    <Space wrap align="start" size="middle">
      <QuickIdentity />
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
}: {
  variants?: Variant[];
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
        extra="暂时不知道型号时可以留空；即使关系已确认，也需补齐候选和数量依据后才能应用。"

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
      <Form.Item name="shared_role_refs" label="共同使用的系统与角色"><SharedRoleSelect /></Form.Item>
      <Form.Item
        name="shared_roles"
        label="历史文字关联（未映射时保留）"
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
