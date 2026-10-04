import { Button, Card, Empty, Space, Table, Tag } from "antd";
import type { Checked, Configuration, IssueAction } from "../types";
import { accessoryOpenItems } from './accessoryOpenItems';

interface OpenItem {
  id: string;
  groupId?: string;
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
  const groups = new Map<string, OpenItem[]>();
  for (const item of items) { const key = item.groupId ?? item.id; groups.set(key, [...(groups.get(key) ?? []), item]); }
  const rows = [...groups.values()].map(members => ({ ...members[0], members, object: [...new Set(members.map(m => m.object))].join('、') }));
  return (
    <Card
      title={`待处理 ${items.length} 项 · ${rows.length} 组原因`}
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
        <Table<OpenItem & { members: OpenItem[] }>
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={rows}
          expandable={{ expandedRowRender: row => <Space orientation="vertical">{row.members.map(item => <div key={item.id}>{item.object}：{item.message} <Button size="small" onClick={() => onAction(item.action ?? { type: 'edit_knowledge' })}>{actionLabel(item.action?.type)}</Button></div>)}</Space>, rowExpandable: row => row.members.length > 1 }}
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
      id: item.check_id ?? `check:${index}:${item.kind}:${item.device_id ?? item.requirement_id ?? "project"}`,
      groupId: item.group_id,
      category: ({ requirements: "需求", selection: "选型配套", commercial: "供货价格", knowledge: "公共知识" } as Record<string, string>)[item.category ?? ""] ?? (item.responsibility === "project" ? "需求" : "公共知识"),
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
  const suggestions: OpenItem[] = checked.suggestions.flatMap(item => accessoryOpenItems(item, configuration));
  const prices: OpenItem[] = (checked.quotation_output?.issues ?? []).map((item, index) => ({
    id: `price:${item.device_id}:${index}`, category: '供货价格', object: deviceNames.get(item.device_id) ?? '报价',
    message: item.message, status: 'unknown', href: '', action: { type: 'edit_price', device_id: item.device_id },
  }));
  return [...checks, ...suggestions, ...prices];
}

function actionLabel(type?: string) {
  return ({ edit_quantity_inputs: '补填数量需求', select_candidate: '选择产品', edit_supply: '分配供货', edit_resources: '补充需求',
    edit_price: '处理报价', add_system: '建立系统', add_requirement: '添加角色需求', edit_requirement: '关联系统角色', assign_device: '关联用途', edit_accessory: '处理配套', edit_definition: '维护系统知识', edit_system_inputs: '填写项目需求', edit_inspection: '维护用途检查' } as Record<string, string>)[type ?? ''] ?? '补充知识依据';
}
