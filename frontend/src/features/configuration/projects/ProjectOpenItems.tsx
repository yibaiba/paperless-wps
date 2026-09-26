import { Button, Card, Empty, Space, Table, Tag } from "antd";
import type { Checked, Configuration } from "../types";

interface OpenItem {
  id: string;
  category: string;
  object: string;
  message: string;
  status: "unknown" | "conflict";
}

export function ProjectOpenItems({
  checked,
  configuration,
}: {
  checked?: Checked;
  configuration: Configuration;
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
            { title: "类型", dataIndex: "category" },
            { title: "对象", dataIndex: "object" },
            { title: "问题", dataIndex: "message" },
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
      category: checkLabel(item.kind),
      object:
        deviceNames.get(item.device_id ?? "") ??
        requirementNames.get(item.requirement_id ?? "") ??
        "项目配置",
      message:
        item.message ??
        (item.resource
          ? `${item.resource} 需要 ${item.required} ${item.unit}，现有容量 ${item.capacity ?? "未知"}`
          : "缺少足够的已确认依据"),
      status: item.status === "conflict" ? "conflict" : "unknown",
    }));
  const suggestions: OpenItem[] = checked.suggestions
    .filter((item) => item.status !== "pass")
    .map((item) => ({
      id: `suggestion:${item.id}`,
      category: "配套需求",
      object: item.need_name || item.rule.name,
      message: item.missing_information?.join("；") || "配套条件尚未确认",
      status: item.status === "conflict" ? "conflict" : "unknown",
    }));
  return [...checks, ...suggestions];
}

function checkLabel(kind: string) {
  return {
    selection: "角色选型",
    compatibility: "产品适配",
    sharing: "共用部署",
    capacity: "资源容量",
    accessory_allocation: "配套分配",
  }[kind] ?? kind;
}
