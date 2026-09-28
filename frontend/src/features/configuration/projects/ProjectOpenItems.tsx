import { Button, Card, Empty, Space, Table, Tag } from "antd";
import type { Checked, Configuration, IssueAction } from "../types";
import { checkLabels } from "./checkLabels";

interface OpenItem {
  id: string;
  category: string;
  object: string;
  message: string;
  status: "unknown" | "conflict";
  href: string;
  action?: IssueAction;
}

export function ProjectOpenItems({
  checked,
  configuration,
  onAction,
}: {
  checked?: Checked;
  configuration: Configuration;
  onAction: (action: IssueAction) => void;
}) {
  const items = openItems(checked, configuration);
  return (
    <Card
      title={`待确认事项 ${items.length}`}
      extra={
        <Space>
          <Button href="/organize">产品整理</Button>
          <Button href="/knowledge">搭配知识</Button>
        </Space>
      }
    >
      {!items.length ? (
        <Empty description="当前检查没有资料不足或冲突事项" />
      ) : (
        <Table<OpenItem>
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={items}
          columns={[
            { title: "类型", dataIndex: "category", filters: [...new Set(items.map((item) => item.category))].map((value) => ({ text: value, value })), onFilter: (value, item) => item.category === value },
            { title: "对象", dataIndex: "object" },
            { title: "问题", dataIndex: "message" },
            { title: "维护入口", render: (_, item) => <Button onClick={() => onAction(item.action ?? { type: "edit_knowledge" })}>{actionLabel(item.action?.type)}</Button> },
            {
              title: "状态",
              render: (_, item) => (
                <Tag color={item.status === "conflict" ? "red" : "gold"}>
                  {item.status === "conflict" ? "明确冲突" : "资料不足"}
                </Tag>
              ),
            },
          ]}
        />
      )}
    </Card>
  );
}

function openItems(checked: Checked | undefined, configuration: Configuration) {
  if (!checked) return [];
  const deviceNames = new Map(configuration.devices.map((item) => [item.id, item.name]));
  const requirementNames = new Map(
    configuration.requirements.map((item) => [item.id, item.role]),
  );
  const checks: OpenItem[] = checked.checks
    .filter((item) => item.status !== "pass")
    .map((item, index) => ({
      id: `check:${index}:${item.kind}:${item.device_id ?? item.requirement_id ?? "project"}`,
      category: item.responsibility === "project" ? checkLabels.project_configuration : checkLabels[item.kind] ?? item.kind,
      action: item.action,
      object:
        deviceNames.get(item.device_id ?? "") ??
        requirementNames.get(item.requirement_id ?? "") ??
        configuration.systems.find((system) => system.id === item.system_id)?.name ??
        "项目配置",
      message:
        item.message ??
        (item.resource
          ? `${item.resource} 需要 ${item.required} ${item.unit}，现有容量 ${item.capacity ?? "未知"}`
          : "缺少足够的已确认依据"),
      status: item.status === "conflict" ? "conflict" : "unknown",
      href: item.kind === "coverage" ? "/knowledge?view=systems" : "/knowledge?" + new URLSearchParams({
        variant: configuration.devices.find((d) => d.id === item.device_id)?.variant_id ?? "",
      }),
    }));
  const suggestions: OpenItem[] = checked.suggestions
    .filter((item) => item.selected !== false && (item.status !== "pass" || Number(item.missing ?? 0) > 0))
    .map((item) => ({
      id: `suggestion:${item.id}`,
      category: item.status === "pass" ? "配套缺量" : "配套依据",
      action: { type: item.missing_information?.length ? "edit_knowledge" : "edit_accessory", demand_id: item.id, rule_id: item.rule.id, variant_id: configuration.devices.find((d) => d.id === item.scope_id)?.variant_id },
      object: item.need_name || item.rule.name,
      href: "/knowledge?" + new URLSearchParams({ rule: item.rule.id }),
      message: item.status === "pass" ? `需要 ${item.required}，已分配 ${item.existing}，还缺 ${item.missing}` : item.missing_information?.join("；") || "配套条件尚未确认",
      status: item.status === "conflict" ? "conflict" : "unknown",
    }));
  return [...checks, ...suggestions];
}

function actionLabel(type?: string) {
  return ({ select_candidate: '选择产品', edit_supply: '分配供货', edit_resources: '补充需求',
    add_system: '建立系统', add_requirement: '添加角色需求', edit_requirement: '关联系统角色', assign_device: '关联用途', edit_accessory: '处理配套', edit_definition: '维护系统知识', edit_system_inputs: '填写项目需求', edit_inspection: '维护用途检查' } as Record<string, string>)[type ?? ''] ?? '补充知识依据';
}
