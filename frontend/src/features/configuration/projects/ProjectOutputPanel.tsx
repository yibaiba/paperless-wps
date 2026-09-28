import { useState } from "react";
import { Alert, Empty, Segmented, Space, Table, Tag, Typography } from "antd";
import type { ProjectOutput, ProjectOutputLine } from "../types";

export function ProjectOutputPanel({
  output,
  stale,
}: {
  output: ProjectOutput;
  stale: boolean;
}) {
  const [mode, setMode] = useState("devices");
  const lines = mode === "purchase" ? output.procurement_lines ?? [] : output.lines;
  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Alert
        showIcon
        type={stale ? "warning" : output.status === "confirmed" ? "success" : "info"}
        title={outputTitle(output, stale)}
        description={outputDescription(output, stale)}
      />
      {output.calculation_version === 3 ? <Segmented value={mode} onChange={setMode} options={[{ value: "devices", label: "全部部署设备" }, { value: "purchase", label: "本次采购" }]} /> : <Alert type="warning" title="历史设备配置清单，尚未区分供货来源" />}
      {lines.length ? (
        <Table<ProjectOutputLine>
          rowKey="device_id"
          dataSource={lines}
          pagination={false}
          scroll={{ x: 1180 }}
          columns={[
            { title: "名称", dataIndex: "name", width: 180 },
            { title: "型号", dataIndex: "model", width: 130 },
            { title: "规格", width: 240, render: (_, line) => <Typography.Paragraph ellipsis={{ rows: 3, expandable: true, symbol: "查看完整参数" }}>{line.specification}</Typography.Paragraph> },
            { title: "类型", render: (_, line) => kindLabel(line.kind), width: 80 },
            { title: "数量", render: (_, line) => `${line.quantity} ${line.unit}`, width: 90 },
            {
              title: "服务系统与角色",
              width: 280,
              render: (_, line) => (
                <Space wrap size={[4, 4]}>
                  {line.consumers.map((consumer) => (
                    <Tag
                      key={`${consumer.requirement_id}:${consumer.via}`}
                      color={consumer.via === "accessory" ? "blue" : "default"}
                    >
                      {consumer.system_name} / {consumer.role}
                    </Tag>
                  ))}
                  {!line.consumers.length ? (
                    <Typography.Text type="secondary">未分配</Typography.Text>
                  ) : null}
                </Space>
              ),
            },
            {
              title: "价格来源值",
              width: 220,
              render: (_, line) => <PriceValues prices={line.prices} />,
            },
            {
              title: "资料来源",
              width: 160,
              render: (_, line) => sourceLabel(line),
            },
          ]}
        />
      ) : (
        <Empty description={mode === "purchase" && output.lines.length ? "当前没有明确列为本次采购的数量；已有设备与供货待确认项仍在部署清单中。" : "选择产品并完成检查后生成业务清单"} />
      )}
    </Space>
  );
}

function PriceValues({ prices }: { prices: Record<string, string> }) {
  const entries = Object.entries(prices);
  if (!entries.length) return <Typography.Text type="secondary">原资料未提供</Typography.Text>;
  return (
    <Space orientation="vertical" size={2}>
      {entries.map(([label, value]) => (
        <Typography.Text key={label}>{label}：{value}</Typography.Text>
      ))}
    </Space>
  );
}

function sourceLabel(line: ProjectOutputLine) {
  if (!line.source.sheet) return "来源记录已冻结";
  return `${line.source.sheet}${line.source.row ? ` · 第 ${line.source.row} 行` : ""}`;
}

function outputTitle(output: ProjectOutput, stale: boolean) {
  if (stale) return "业务清单需要重新检查";
  if (output.calculation_version < 3 && output.status === "confirmed") return "历史检查通过（非人工确认）";
  return output.status === "confirmed" ? "已人工确认的项目清单" : "草稿设备与采购清单";
}

function outputDescription(output: ProjectOutput, stale: boolean) {
  if (stale) return "当前配置已变化，表中仍显示上一次检查结果。";
  if (output.status === "confirmed") {
    return "该清单已通过当前知识快照下的选型、配套、共享和容量检查。";
  }
  if (output.ready_for_confirmation) return "检查与资料范围核对已满足确认条件，保存后可人工确认本项目版本。价格仍保留原始来源值。";
  return "清单保留原始产品资料和价格字段，但存在未确认事项，不能作为已审核报价。";
}

function kindLabel(kind: ProjectOutputLine["kind"]) {
  return {
    hardware: "硬件",
    software: "软件",
    license: "授权",
    accessory: "配件",
  }[kind];
}
