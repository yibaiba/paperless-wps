import { useState } from "react";
import { Alert, Button, Space, Typography } from "antd";
import type { Configuration, IncludedAllocation, Suggestion } from "../types";
import { Status } from "../shared";
import { IncludedReviewDialog } from "./IncludedReviewDialog";

export function IncludedAllocationRows({ configuration, suggestion, disabled, onChange }: {
  configuration: Configuration; suggestion: Suggestion; disabled: boolean;
  onChange?: (configuration: Configuration) => void;
}) {
  const [editingId, setEditingId] = useState<string>();
  const allocations = (configuration.included_allocations ?? []).filter((a) => a.demand_id === suggestion.id);
  const offerFor = (a: IncludedAllocation) => suggestion.included_offers?.find((o) => o.device_id === a.device_id && o.included_item_id === a.included_item_id);
  const editing = allocations.find((a) => a.id === editingId);
  const editingOffer = editing ? offerFor(editing) : undefined;
  return <>
    {editing && editingOffer && onChange ? <IncludedReviewDialog key={editing.id} configuration={configuration} allocation={editing} offer={editingOffer}
      disabled={disabled || suggestion.selected === false} onApply={onChange} onClose={() => setEditingId(undefined)} /> : null}
    {allocations.map((allocation) => {
      const check = suggestion.included_allocation_checks?.find((c) => c.allocation_id === allocation.id);
      const offer = offerFor(allocation);
      const name = configuration.devices.find((d) => d.id === allocation.device_id)?.name ?? allocation.device_id;
      return <Alert key={allocation.id} type={disabled ? "info" : check?.status === "conflict" ? "error" : check?.status === "pass" ? "success" : "warning"}
        title={<Space wrap><Typography.Text strong>{name} · {check?.included_name || "已含内容"}</Typography.Text>
          {disabled ? "待重新检查" : <Status value={check?.status ?? "unknown"} />}
        </Space>}
        description={<Space orientation="vertical" style={{ width: "100%" }}>
          <Typography.Text>已关联 {allocation.quantity} · 本次有效抵扣 {disabled ? "待检查" : check?.counted_quantity ?? "待检查"}</Typography.Text>
          <Typography.Text>{disabled ? "配置正在变化，以下为上次检查依据。" : check?.message ?? "此保存版本没有逐项抵扣结果，请检查当前配置。"}</Typography.Text>
          <Typography.Text type="secondary">采用修订 v{allocation.host_variant_revision} · 当前项目修订 {check?.current_host_variant_revision ? `v${check.current_host_variant_revision}` : "待检查"} · 宿主总含量 {check?.capacity ?? "未知"} · 共关联 {check?.allocated_quantity ?? "待检查"}</Typography.Text>
          <Typography.Text>采用说明：{allocation.evidence}</Typography.Text>
          {check?.current_evidence ? <Typography.Text>当前包含依据：{check.current_evidence}</Typography.Text> : null}
          <Space wrap>
            {offer?.status === "pass" ? <Button disabled={disabled || !onChange || suggestion.selected === false} onClick={() => setEditingId(allocation.id)}>修改数量／重新核对</Button> : null}
            <Button disabled={disabled || !onChange} onClick={() => onChange?.({ ...configuration,
              included_allocations: configuration.included_allocations?.filter((a) => a.id !== allocation.id),
            })}>移除已含抵扣</Button>
          </Space>
        </Space>} />;
    })}
  </>;
}
