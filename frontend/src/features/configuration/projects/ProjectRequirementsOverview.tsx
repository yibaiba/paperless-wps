import { Button, Card, Descriptions, Empty, Space, Tag, Typography } from "antd";
import type { Configuration } from "../types";

export function ProjectRequirementsOverview({
  configuration,
  selectedSystemId,
  onEditInputs,
  onAddRequirement,
}: {
  configuration: Configuration;
  selectedSystemId?: string;
  onEditInputs: (systemId: string) => void;
  onAddRequirement: (systemId: string) => void;
}) {
  const system = configuration.systems.find((item) => item.id === selectedSystemId);
  if (!system) return <Empty description="从左侧选择一个系统，核对版本、规模和角色需求" />;
  const room = configuration.rooms.find((item) => item.id === system.room_id);
  const requirements = configuration.requirements.filter((item) => item.system_id === system.id);
  return <Space orientation="vertical" size="large" style={{ width: "100%" }}>
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>{system.name}</Typography.Title>
      <Typography.Text type="secondary">先确认业务需求，再进入设备选型。缺少的输入会在检查中定位到本系统。</Typography.Text>
    </div>
    <Descriptions bordered column={2} size="small" items={[
      { key: "room", label: "房间", children: room?.name ?? "待关联" },
      { key: "kind", label: "系统类型", children: system.kind },
      { key: "definition", label: "系统定义", children: system.definition_id ? "已关联" : "待关联" },
      { key: "package", label: "资料版本", children: system.knowledge_package_id ? "已关联" : "待关联" },
      { key: "features", label: "已启用功能", span: 2, children: system.features?.length
        ? <Space wrap>{system.features.map((feature) => <Tag key={feature}>{feature}</Tag>)}</Space>
        : "尚未明确" },
    ]} />
    <Card size="small" title={`角色需求 ${requirements.length} 项`} extra={<Space>
      <Button onClick={() => onEditInputs(system.id)}>填写规模与环境</Button>
      <Button type="primary" onClick={() => onAddRequirement(system.id)}>添加角色需求</Button>
    </Space>}>
      {requirements.length ? <Space wrap>{requirements.map((item) => <Tag key={item.id}
        color={item.device_id || item.allocations?.length ? "green" : "gold"}>{item.role} · {item.device_id || item.allocations?.length ? "已选型" : "待选型"}</Tag>)}</Space>
        : <Typography.Text type="secondary">尚未建立角色需求。系统可根据已确认定义预览应有角色，也可先人工添加。</Typography.Text>}
    </Card>
  </Space>;
}
