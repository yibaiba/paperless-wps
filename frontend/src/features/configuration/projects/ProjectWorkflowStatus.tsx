import { Alert, Button, Collapse, Space, Steps, Tag } from "antd";
import type { ProjectReadiness, ReadinessStage } from "../types";
import { checkLabels } from "./checkLabels";

export function ProjectWorkflowStatus({
  readiness,
  stale,
  onViewChecks,
  onCheck,
  busy,
  checking,
}: {
  readiness: ProjectReadiness;
  stale: boolean;
  onViewChecks: () => void;
  onCheck: () => void;
  busy: boolean;
  checking: boolean;
}) {
  const firstIncomplete = readiness.stages.findIndex((item) => item.status !== "pass");
  const current = firstIncomplete < 0 ? readiness.stages.length - 1 : firstIncomplete;
  const status = stale ? "unknown" : readiness.status;
  return (
    <Collapse items={[{ key: 'progress', label: <Space wrap>
      <span>方案进度</span>
      <Tag style={{ whiteSpace: "normal" }} color={status === 'conflict' ? 'red' : status === 'pass' ? 'green' : 'gold'}>{stale ? "修改后待检查" : status === "pass" ? "已通过已知检查" : pendingSummary(readiness)}</Tag>
    </Space>, extra: <Space onKeyDown={(event) => event.stopPropagation()}>
      <Button size="small" disabled={busy} loading={checking} onClick={(event) => { event.stopPropagation(); onCheck(); }}>检查清单</Button>
      <Button type="link" size="small" onClick={(event) => { event.stopPropagation(); onViewChecks(); }}>处理问题与配套</Button>
    </Space>, children: <>
        <Space wrap>
          {stale ? <Tag color="gold">以下为上次检查数据</Tag> : null}
          <Tag>{readiness.counts.requirements} 个角色需求</Tag>
          <Tag>{readiness.counts.devices} 项实际配置</Tag>
          {readiness.counts.open_accessories ? (
            <Tag color="gold">{readiness.counts.open_accessories} 项待补配套</Tag>
          ) : null}
        </Space>
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
    </> }]} />
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
  if (readiness.ready_for_confirmation) return "已满足已知检查和资料覆盖要求，请保存后明确确认该修订。";
  if (readiness.ready_for_confirmed_output) {
    return "清单与拓扑使用同一份项目配置，可以继续生成确认版业务输出。";
  }
  if (!readiness.ready_for_draft) {
    return "先建立系统角色并选择产品，系统才会形成项目清单。";
  }
  return `${pendingSummary(readiness)}。检查口径由知识维护者确认；资源需求由项目人员填写。配套资料不足不等于已确定缺件。`;
}

function pendingSummary(readiness: ProjectReadiness) {
  const counts = readiness.counts;
  const parts = Object.entries(readiness.pending_by_kind ?? {})
    .map(([kind, count]) => `${checkLabels[kind] ?? kind} ${count} 项待确认`);
  if (!readiness.pending_by_kind && counts.unknowns) parts.push(`检查 ${counts.unknowns} 项待确认`);
  if (counts.accessory_unknowns) parts.push(`配套需求或依据 ${counts.accessory_unknowns} 项待确认`);
  if (counts.open_accessories) parts.push(`配套缺量 ${counts.open_accessories} 项`);
  const conflicts = counts.conflicts + (counts.accessory_conflicts ?? 0);
  if (conflicts) parts.unshift(`明确冲突 ${conflicts} 项`);
  return parts.join(" · ") || "请展开查看方案进度";
}
