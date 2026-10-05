import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, App, Button, Checkbox, Modal, Space, Table, Typography } from "antd";
import { api } from "../../../shared/api";
import { ROOT, Status } from "../shared";
import { BusinessChangeTable } from "./BusinessChangeTable";
import { checkLabels } from "./checkLabels";
import type { ChangePreview, Check, Configuration } from "../types";
import type { RecheckInput } from './drafts/usePersistentDraft';

export function ProjectChangePanel({ projectId, revision, configuration, refresh, cleanup, current, onApply, onClose }: {
  projectId: string; revision: number; configuration: Configuration; refresh: boolean; cleanup: boolean;
  current: () => Configuration; onApply: (request: RecheckInput) => Promise<unknown>; onClose: () => void;
}) {
  const [upgradeDecisions, setUpgradeDecisions] = useState(false);
  const [baselineRequest] = useState(() => ({ expected_revision: revision, configuration: structuredClone(configuration), refresh_knowledge: refresh, upgrade_calculation: refresh, cleanup_allocations: cleanup }));
  const request = { ...baselineRequest, upgrade_decisions: upgradeDecisions };
  const { message } = App.useApp();
  const query = useQuery({ queryKey: ["configuration", "change-preview", projectId, request], retry: false, refetchOnWindowFocus: false,
    queryFn: () => api<ChangePreview>(`${ROOT}/projects/${projectId}/change-preview`, { method: "POST", body: JSON.stringify(request) }),
  });
  const stale = JSON.stringify(current()) !== JSON.stringify(request.configuration);
  const apply = useMutation({
    mutationFn: () => {
      if (JSON.stringify(current()) !== JSON.stringify(request.configuration)) throw new Error("草稿已变化，请关闭后重新预览");
      const { configuration: _configuration, expected_revision, ...flags } = request;
      return onApply({ ...flags, expected_project_revision: expected_revision, fingerprint: query.data!.fingerprint });
    },
    onSuccess: onClose, onError: (e) => message.error(e.message),
  });
  return <Modal open title={refresh ? "预览资料与计算升级" : "本次改单影响预览"} width={1100} onCancel={onClose} footer={<Space>
    <Button onClick={onClose}>关闭预览</Button>
    <Button type="primary" disabled={!query.data || stale} loading={apply.isPending} onClick={() => apply.mutate()}>应用到草稿</Button>
  </Space>}>
    <Alert showIcon type="info" title="预览不会修改已保存项目" description="应用后可以整次撤销；保存才产生项目新版本。减少数量不自动删除采购设备。" />
    {configuration.decision_runtime !== "zen-v1" ? <Checkbox checked={upgradeDecisions} onChange={e => setUpgradeDecisions(e.target.checked)}>预览采用 ZEN 决策（单独勾选不会刷新产品、知识或报价）</Checkbox> : <Typography.Text>本项目使用 ZEN 固定版本决策</Typography.Text>}
    {query.error ? <Alert type="error" title={query.error.message} /> : null}
    {stale ? <Alert type="warning" title="草稿已变化，请重新预览" /> : null}
    <Typography.Title level={5}>项目业务变化</Typography.Title>
    <BusinessChangeTable changes={query.data?.changes} loading={query.isLoading} />
    <Typography.Title level={5}>采购数量与资料变化</Typography.Title>
    <BusinessChangeTable changes={query.data?.procurement_changes} loading={query.isLoading} />
    <Typography.Title level={5}>用途与分配变化</Typography.Title>
    <Table rowKey="device_id" size="small" pagination={{ pageSize: 5 }} dataSource={query.data?.usage_changes} columns={[
      { title: '设备', render: (_, c) => configuration.devices.find(d => d.id === c.device_id)?.name ?? c.device_id },
      { title: '原分配占量', render: (_, c) => c.previous?.quantity_summary?.reserved_quantity ?? '历史明细未记录' },
      { title: '新分配占量', render: (_, c) => c.current?.quantity_summary?.reserved_quantity ?? '未分配' },
      { title: '独立／共用／未分配', render: (_, c) => c.current?.quantity_summary ? `${c.current.quantity_summary.independent_quantity} / ${c.current.quantity_summary.shared_quantity} / ${c.current.quantity_summary.unassigned_quantity}` : '无设备' },
    ]} />
    <Typography.Title level={5}>检查结论变化</Typography.Title>
    <Table rowKey={(_, i) => String(i)} size="small" pagination={{ pageSize: 5 }} dataSource={query.data?.check_changes} columns={[
      { title: '原检查', render: (_, change) => checkResult(change.previous) },
      { title: '新检查', render: (_, change) => checkResult(change.current) },
    ]} />
    <Typography.Title level={5}>变化后的检查</Typography.Title>
    <Table rowKey={(_, i) => String(i)} size="small" dataSource={query.data?.checked.checks.filter((c) => c.status !== "pass")} columns={[
      { title: "检查", render: (_, c) => checkLabels[c.kind] ?? c.kind }, { title: "状态", render: (_, c) => <Status value={c.status} /> }, { title: "说明", render: (_, c) => c.message ?? `${c.resource ?? "适配"}：需求 ${c.required ?? "见条件"}，容量 ${c.capacity ?? "待核对"}` },
    ]} />
  </Modal>;
}

function checkResult(check: Check | null) {
  if (!check) return <Typography.Text type="secondary">无此检查</Typography.Text>;
  return <Space><Status value={check.status} /><span>{checkLabels[check.kind] ?? check.kind}：{check.message ?? `需求 ${check.required ?? '见条件'}，容量 ${check.capacity ?? '待核对'} ${check.unit ?? ''}`}</span></Space>;
}
