import { useState } from "react";
import { Button, Input, InputNumber, Select, Space, Typography } from "antd";
import type { Configuration, Suggestion } from "../types";
import { IncludedAllocationRows } from "./IncludedAllocationRows";

interface Props {
  configuration: Configuration;
  suggestion: Suggestion;
  disabled: boolean;
  onChange?: (configuration: Configuration) => void;
}

export function IncludedContentPanel({ configuration, suggestion, disabled, onChange }: Props) {
  const [selected, setSelected] = useState<string>();
  const [quantity, setQuantity] = useState<string | null>(null);
  const [evidence, setEvidence] = useState("");
  const offers = suggestion.included_offers ?? [];
  const allocations = (configuration.included_allocations ?? []).filter((a) => a.demand_id === suggestion.id);
  const offer = offers.find((o) => JSON.stringify([o.device_id, o.included_item_id]) === selected);
  const deviceName = (id: string) => configuration.devices.find((d) => d.id === id)?.name ?? id;
  if (!offers.length && !allocations.length) return null;
  const canApply = !disabled && !!onChange && suggestion.selected !== false && suggestion.status === "pass"
    && offer?.status === "pass" && !!quantity && Number(quantity) > 0 && evidence.trim()
    && Number(quantity) <= Number(offer.available) && Number(quantity) <= Number(suggestion.missing);
  return <Space orientation="vertical" style={{ width: "100%", marginBottom: 16 }}>
    <Typography.Text strong>产品已含内容抵扣</Typography.Text>
    <Typography.Text type="secondary">另行配套 {suggestion.separately_allocated ?? "0"} · 已含抵扣 {suggestion.included_quantity ?? "0"}。抵扣不新增采购项。</Typography.Text>
    <IncludedAllocationRows configuration={configuration} suggestion={suggestion} disabled={disabled} onChange={onChange} />
    {offers.length ? <>
      <Select aria-label="选择产品已含内容" style={{ width: "100%" }} placeholder="选择产品已含内容" value={selected} onChange={setSelected}
        options={offers.map((o) => ({ value: JSON.stringify([o.device_id, o.included_item_id]), label: `${deviceName(o.device_id)} · ${o.name} · 剩余 ${o.available ?? "未知"}（每单位 ${o.per_unit ?? "未知"}）` }))} />
      {offer ? <Typography.Paragraph type={offer.status === "pass" ? "secondary" : "warning"}>
        {offer.reason}；配置 v{offer.host_variant_revision}；依据：{offer.evidence || "待补充"}
      </Typography.Paragraph> : null}
      <Space wrap>
        <InputNumber aria-label="已含抵扣数量" stringMode value={quantity} onChange={setQuantity} placeholder="抵扣数量" />
        <Input aria-label="已含抵扣确认依据" value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="本次采用包含依据的说明" style={{ width: 300 }} />
        <Button disabled={!canApply} onClick={() => {
          if (!offer || !quantity) return;
          onChange?.({ ...configuration, included_allocations: [...(configuration.included_allocations ?? []), {
            id: crypto.randomUUID(), demand_id: suggestion.id, device_id: offer.device_id,
            included_item_id: offer.included_item_id, host_variant_id: offer.host_variant_id,
            host_variant_revision: offer.host_variant_revision, quantity, evidence: evidence.trim(),
          }] });
        }}>确认已含抵扣</Button>
      </Space>
    </> : null}
  </Space>;
}
