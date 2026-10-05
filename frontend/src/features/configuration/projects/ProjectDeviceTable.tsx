import { Button, Space, Table, Tag, Typography } from "antd";
import type {
  Configuration,
  Deployment,
  DeviceUsage,
} from "../types";

export function ProjectDeviceTable({
  configuration,
  usages,
  stale,
  onEdit,
  onAddToDrawing,
}: {
  configuration: Configuration;
  usages: DeviceUsage[];
  stale?: boolean;
  onEdit: (id: string) => void;
  onAddToDrawing: (id: string) => void;
}) {
  const usageByDevice = new Map(usages.map((item) => [item.device_id, item]));
  return (
    <Table<Deployment>
      rowKey="id"
      dataSource={configuration.devices}
      virtual
      pagination={false}
      scroll={{ x: 760, y: 560 }}
      columns={[
        { title: "产品 / 型号", width: 270, render: (_, device) => <div>
          <Typography.Text strong>{device.name}</Typography.Text>
          <Typography.Text type="secondary" className="project-device-model">{device.variant_snapshot?.product.model || "型号待确认"}</Typography.Text>
        </div> },
        { title: "类型", width: 70, render: (_, device) => kindLabel(device.kind) },
        { title: "部署数量", width: 90, render: (_, device) => `${device.quantity} ${device.source_snapshot?.unit ?? ""}` },
        {
          title: "服务系统与角色",
          render: (_, device) => {
            const consumers = usageByDevice.get(device.id)?.consumers ?? [];
            if (!consumers.length) {
              return <Typography.Text type="secondary">{stale ? "使用关系待重新检查" : "尚未关联"}</Typography.Text>;
            }
            return (
              <Space wrap size={[4, 4]}>
                {consumers.map((consumer) => (
                  <Tag className="project-consumer-tag"
                    key={`${consumer.requirement_id}:${consumer.via}:${consumer.demand_id ?? "direct"}`}
                    color={consumer.via === "accessory" ? "blue" : "default"}
                  >
                    {consumer.system_name} / {consumer.role}
                    {consumer.fulfilled_by_demand_ids?.length ? "（引用已有分配）" : consumer.via === "accessory" ? "（配套）" : ""}
                  </Tag>
                ))}
              </Space>
            );
          },
        },
        {
          title: "操作", width: 145,
          render: (_, device) => (
            <Space>
              <Button type="link" size="small" onClick={() => onEdit(device.id)}>编辑</Button>
              <Button type="text" size="small" onClick={() => onAddToDrawing(device.id)}>放入图纸</Button>
            </Space>
          ),
        },
      ]}
    />
  );
}

function kindLabel(kind: Deployment["kind"]) {
  return {
    hardware: "硬件",
    software: "软件",
    license: "授权",
    accessory: "配件",
  }[kind];
}
