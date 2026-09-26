import { Alert, Card, Space, Steps, Tag } from "antd";
import type { ProjectReadiness, ReadinessStage } from "../types";

export function ProjectWorkflowStatus({
  readiness,
  stale,
}: {
  readiness: ProjectReadiness;
  stale: boolean;
}) {
  const firstIncomplete = readiness.stages.findIndex((item) => item.status !== "pass");
  const current = firstIncomplete < 0 ? readiness.stages.length - 1 : firstIncomplete;
  const status = stale ? "unknown" : readiness.status;
  return (
    <Card
      title="售前配置进度"
      extra={
        <Space wrap>
          <Tag>{readiness.counts.requirements} 个角色需求</Tag>
          <Tag>{readiness.counts.devices} 项实际配置</Tag>
          {readiness.counts.open_accessories ? (
            <Tag color="gold">{readiness.counts.open_accessories} 项待补配套</Tag>
          ) : null}
        </Space>
      }
    >
      <Steps
        responsive
        current={current}
        items={readiness.stages.map((item) => ({
          title: item.label,
          content: item.message,
          status: stepStatus(item, stale),
        }))}
      />
      <Alert
        showIcon
        type={status === "pass" ? "success" : status === "conflict" ? "error" : "warning"}
        title={statusTitle(status, stale)}
        description={statusDescription(readiness, stale)}
        style={{ marginTop: 16 }}
      />
    </Card>
  );
}

function stepStatus(stage: ReadinessStage, stale: boolean) {
  if (stale) return "wait" as const;
  return stage.status === "pass" ? "finish" : stage.status === "conflict" ? "error" : "wait";
}

function statusTitle(status: ProjectReadiness["status"], stale: boolean) {
  if (stale) return "项目配置已有变化，需要重新检查";
  if (status === "pass") return "项目已达到确认版输出条件";
  if (status === "conflict") return "项目存在明确冲突";
  return "项目可以保存草稿，仍有资料或选择待确认";
}

function statusDescription(readiness: ProjectReadiness, stale: boolean) {
  if (stale) return "重新检查后，系统会更新配套、共享、容量和输出状态。";
  if (readiness.ready_for_confirmed_output) {
    return "清单与拓扑使用同一份项目配置，可以继续生成确认版业务输出。";
  }
  if (!readiness.ready_for_draft) {
    return "先建立系统角色并选择产品，系统才会形成项目清单。";
  }
  return `当前有 ${readiness.counts.conflicts} 项冲突、${readiness.counts.unknowns} 项资料不足。`;
}
