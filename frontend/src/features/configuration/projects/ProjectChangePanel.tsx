import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, App, Button, Collapse, Modal, Space, Table, Typography } from "antd";
import { api } from "../../../shared/api";
import { ROOT } from "../shared";
import type { BusinessChange, ChangePreview, Checked, Configuration } from "../types";

export function ProjectChangePanel({ projectId, revision, configuration, refresh, cleanup, current, onApply, onClose }: {
  projectId: string; revision: number; configuration: Configuration; refresh: boolean; cleanup: boolean;
  current: () => Configuration; onApply: (result: Checked) => void; onClose: () => void;
}) {
  const [request] = useState(() => ({ expected_revision: revision, configuration: structuredClone(configuration), refresh_knowledge: refresh, upgrade_calculation: refresh, cleanup_allocations: cleanup }));
  const { message } = App.useApp();
  const query = useQuery({ queryKey: ["configuration", "change-preview", projectId, request], retry: false, refetchOnWindowFocus: false,
    queryFn: () => api<ChangePreview>(`${ROOT}/projects/${projectId}/change-preview`, { method: "POST", body: JSON.stringify(request) }),
  });
  const stale = JSON.stringify(current()) !== JSON.stringify(request.configuration);
  const apply = useMutation({
    mutationFn: () => {
      if (JSON.stringify(current()) !== JSON.stringify(request.configuration)) throw new Error("草稿已变化，请关闭后重新预览");
      return api<Checked>(`${ROOT}/projects/${projectId}/change-apply`, { method: "POST", body: JSON.stringify({ ...request, fingerprint: query.data!.fingerprint }) });
    },
    onSuccess: (checked) => {
      if (JSON.stringify(current()) !== JSON.stringify(request.configuration)) { message.error("等待期间草稿已变化，结果未覆盖当前修改"); return; }
      onApply(checked); onClose();
    }, onError: (e) => message.error(e.message),
  });
  return <Modal open title={refresh ? "预览资料与计算升级" : "本次改单影响预览"} width={1100} onCancel={onClose} footer={<Space>
    <Button onClick={onClose}>关闭预览</Button>
    <Button type="primary" disabled={!query.data || stale} loading={apply.isPending} onClick={() => apply.mutate()}>应用到草稿</Button>
  </Space>}>
    <Alert showIcon type="info" title="预览不会修改已保存项目" description="应用后可以整次撤销；保存才产生项目新版本。减少数量不自动删除采购设备。" />
    {query.error ? <Alert type="error" title={query.error.message} /> : null}
    {stale ? <Alert type="warning" title="草稿已变化，请重新预览" /> : null}
    <Typography.Title level={5}>项目业务变化</Typography.Title>
    <ChangeTable changes={query.data?.changes} loading={query.isLoading} />
    <Typography.Title level={5}>采购数量与资料变化</Typography.Title>
    <ChangeTable changes={query.data?.procurement_changes} loading={query.isLoading} />
    <Typography.Title level={5}>变化后的检查</Typography.Title>
    <Table rowKey={(_, i) => String(i)} size="small" dataSource={query.data?.checked.checks.filter((c) => c.status !== "pass")} columns={[
      { title: "检查", dataIndex: "kind" }, { title: "状态", dataIndex: "status" }, { title: "说明", render: (_, c) => c.message ?? `${c.resource ?? "适配"}：需求 ${c.required ?? "见条件"}，容量 ${c.capacity ?? "待核对"}` },
    ]} />
  </Modal>;
}
function ChangeTable({ changes, loading }: { changes?: BusinessChange[]; loading: boolean }) {
  return <Table<BusinessChange> rowKey={(r) => `${r.kind}:${r.id}`} size="small" loading={loading} dataSource={changes}
    expandable={{ expandedRowRender: (change) => <Collapse items={[{ key: "details", label: "完整字段变化与依据", children: <Space align="start"><pre>{JSON.stringify(change.before, null, 2)}</pre><pre>{JSON.stringify(change.after, null, 2)}</pre></Space> }]} /> }}
    columns={[{ title: "对象", render: (_, c) => `${c.kind} · ${c.id.slice(0, 12)}` },
      { title: "修改前", render: (_, c) => describe(c.before) }, { title: "修改后", render: (_, c) => describe(c.after) }]} />;
}
function describe(value: unknown): string {
  if (value == null) return "无";
  if (typeof value !== "object") return String(value);
  const item = value as Record<string, unknown>;
  const source = typeof item.source === "string" ? ({ purchase: "本次采购", existing: "客户已有", unknown: "供货待确认" }[item.source] ?? item.source) : "";
  if (item.name || item.quantity) return [item.name, item.model, item.quantity ? `数量 ${item.quantity}` : "", source].filter(Boolean).join(" · ");
  return JSON.stringify(value);
}
