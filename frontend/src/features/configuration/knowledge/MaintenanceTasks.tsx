import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Collapse, Space, Table, Tag, Typography } from "antd";
import { api } from "../../../shared/api";
import { ROOT } from "../shared";
import { checkLabels } from "../projects/checkLabels";
import type { IssueAction } from "../types";
interface Task {
  id: string; kind: string; title: string; owner: string; action: IssueAction;
  project_count: number; newer_knowledge_available: boolean;
  impacts: { project_id: string; project_name: string; revision: number; objects: string[] }[];
  evidence: { evidence?: string; name?: string }[];
}
export const maintenanceKey = ["configuration", "maintenance-tasks"] as const;
export function MaintenanceTasks() {
  const query = useQuery({ queryKey: maintenanceKey, queryFn: () => api<{ items: Task[]; total: number; project_count: number }>(ROOT + "/maintenance-tasks") });
  return <Card title="集中处理知识缺口" extra={<Button loading={query.isFetching} onClick={() => query.refetch()}>刷新待办</Button>}>
    <Typography.Paragraph type="secondary">同一知识修订的缺口集中维护，展开查看受影响项目。依据各项目最新保存版本，不包含未保存草稿；补充知识后，项目需主动重新检查。</Typography.Paragraph>
    {query.error ? <Alert type="error" title={query.error.message} /> : null}
    <Table<Task> rowKey="id" loading={query.isLoading} dataSource={query.data?.items} pagination={{ pageSize: 10 }} columns={[
      { title: "待维护知识", dataIndex: "title" },
      { title: "类型", render: (_, t) => checkLabels[t.kind] ?? (t.kind === "accessory" ? "配套依据" : t.kind) },
      { title: "影响项目", render: (_, t) => `${t.project_count} 个项目` },
      { title: "处理状态", render: (_, t) => <Tag color="gold">{t.newer_knowledge_available ? "资料已更新，项目待复查" : "需维护依据"}</Tag> },
      { title: "责任", dataIndex: "owner" },
      { title: "操作", render: (_, t) => <Button href={actionLink(t.action)}>维护知识</Button> },
    ]} expandable={{ expandedRowRender: (task) => <Space orientation="vertical" style={{ width: "100%" }}>
      {task.impacts.map((impact, i) => <div key={`${impact.project_id}:${i}`}><Button type="link" href={`/configuration/${impact.project_id}`}>{impact.project_name} · v{impact.revision}</Button>{impact.objects.join("、")}</div>)}
      <Collapse items={[{ key: "evidence", label: "查看检查引用的依据", children: task.evidence.length ? task.evidence.map((e, i) => <Typography.Paragraph key={i}>{e.name} {e.evidence}</Typography.Paragraph>) : "尚无已确认依据" }]} />
    </Space> }} />
  </Card>;
}
function actionLink(action: IssueAction) {
  if (action.type === "edit_inspection") return "/knowledge?" + new URLSearchParams({ view: "inspections", ...(action.profile_id ? { profile: action.profile_id } : {}) });
  if (action.type === "edit_definition") return "/knowledge?view=systems";
  return "/knowledge?" + new URLSearchParams(action.rule_id ? { rule: action.rule_id } : { variant: action.variant_id ?? "" });
}
