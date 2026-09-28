import { useState } from "react";
import { Alert, Button, Card, Descriptions, InputNumber, Switch, Tag, Select, Space, Typography } from "antd";
import type { ApplyChoice, Configuration, Suggestion, Variant } from "./types";
import { Status, sourceOptions, variantOptions } from "./shared";
import { NewSupplyDialog } from "./projects/NewSupplyDialog";
import { QuantityEvidence } from "./projects/QuantityEvidence";

interface Props {
  suggestion: Suggestion;
  configuration: Configuration;
  variants?: Variant[];
  busy: boolean;
  stale: boolean;
  onApply: (suggestion: Suggestion, choice: ApplyChoice) => void;
  onChoice?: (demandId: string, selected: boolean) => void;
}

export function AccessorySuggestionCard(props: Props) {
  const { suggestion, configuration, variants, busy, stale, onApply } = props;
  const [action, setAction] = useState<"new" | "existing">("new");
  const [variantId, setVariantId] = useState<string>();
  const [sourceId, setSourceId] = useState<string>();
  const [deviceId, setDeviceId] = useState<string>();
  const [quantity, setQuantity] = useState<string>();
  const [supplyOpen, setSupplyOpen] = useState(false);
  const candidates = variants?.filter((item) =>
    suggestion.rule.target_variant_ids.includes(item.id),
  );
  const chosenId = variantId ?? (candidates?.length === 1 ? candidates[0].id : undefined);
  const variant = candidates?.find((item) => item.id === chosenId);
  const chosenSource =
    sourceId ?? (variant?.source_ids.length === 1 ? variant.source_ids[0] : undefined);
  const existing = configuration.devices.filter((item) =>
    suggestion.rule.target_variant_ids.includes(item.variant_id),
  );
  const hasMissing = suggestion.missing !== null && Number(suggestion.missing) > 0;
  const amount = quantity ?? (hasMissing ? suggestion.missing! : undefined);
  const applicable =
    !busy && !stale && suggestion.status === "pass" && hasMissing && suggestion.selected !== false;
  return (
    <Card
      size="small"
      title={suggestion.need_name || suggestion.rule.need_name || suggestion.rule.name}
      extra={<Status value={suggestion.status} />}
    >
      {supplyOpen ? <NewSupplyDialog name={variant?.name ?? "配套设备"} onClose={() => setSupplyOpen(false)} onConfirm={(supply) => {
        onApply(suggestion, { variantId: chosenId!, sourceId: chosenSource!, quantity: amount, supplySource: supply.source, supplyEvidence: supply.evidence });
        setSupplyOpen(false);
      }} /> : null}
      <Space wrap style={{ marginBottom: 12 }}>
        <Tag>{({ required: "必需", recommended: "推荐", optional: "可选" })[suggestion.rule.accessory_type]}</Tag>
        {configuration.calculation_version === 3 && suggestion.rule.accessory_type !== "required" ? <>
          <Switch aria-label="本次选用配套" checked={suggestion.selected} disabled={busy || stale}
            onChange={(selected) => props.onChoice?.(suggestion.id, selected)} />
          <Typography.Text>{suggestion.selected ? "本次已选用" : "本次未选用，不计入需求"}</Typography.Text>
        </> : null}
      </Space>
      <Descriptions
        size="small"
        column={{ xs: 1, sm: 2, md: 4 }}
        items={[
          { key: "scope", label: "计算范围", children: scopeLabel(suggestion, configuration) },
          { key: "required", label: "需要", children: suggestion.required ?? "待确认" },
          { key: "existing", label: "已分配", children: suggestion.existing ?? "0" },
          { key: "missing", label: "还缺", children: suggestion.missing ?? "待确认" },
        ]}
      />
      {suggestion.missing_information?.length ? (
        <Alert
          type={suggestion.status === "conflict" ? "error" : "warning"}
          showIcon
          title="尚不能自动补入"
          description={suggestion.missing_information.join("；")}
        />
      ) : null}
      {Number(suggestion.surplus) > 0 ? (
        <Alert type="warning" showIcon title={`当前多出 ${suggestion.surplus}，系统不会自动删除`} />
      ) : null}
      <Typography.Paragraph type="secondary">
        {suggestion.rule.evidence}
        {suggestion.calculation ? `；${suggestion.calculation.engine}：${suggestion.calculation.expression}；输入 ${JSON.stringify(suggestion.calculation.input)}` : ""}
      </Typography.Paragraph>
      <QuantityEvidence suggestion={suggestion} configuration={configuration} />
      {suggestion.consumer_requirement_ids?.length ? (
        <Typography.Paragraph type="secondary">
          服务对象：
          {suggestion.consumer_requirement_ids
            .map((id) => {
              const requirement = configuration.requirements.find((item) => item.id === id);
              const system = configuration.systems.find(
                (item) => item.id === requirement?.system_id,
              );
              return requirement ? `${system?.name ?? "未知系统"} / ${requirement.role}` : id;
            })
            .join("、")}
        </Typography.Paragraph>
      ) : null}
      {hasMissing ? (
        <Space wrap align="end">
          <Select
            value={action}
            style={{ width: 150 }}
            onChange={setAction}
            options={[
              { value: "new", label: "新增清单项" },
              { value: "existing", label: "关联已有设备" },
            ]}
          />
          {action === "new" ? (
            <>
              <Select
                style={{ width: 250 }}
                placeholder="选择配套配置"
                value={chosenId}
                options={variantOptions(candidates)}
                onChange={(value) => {
                  setVariantId(value);
                  setSourceId(undefined);
                }}
              />
              <Select
                style={{ width: 210 }}
                placeholder="选择资料来源"
                value={chosenSource}
                options={sourceOptions(variant)}
                onChange={setSourceId}
              />
            </>
          ) : (
            <Select
              style={{ width: 300 }}
              placeholder="选择已有设备"
              value={deviceId}
              options={existing.map((item) => ({
                value: item.id,
                label: `${item.name} · 可用数量 ${item.quantity}`,
              }))}
              onChange={setDeviceId}
            />
          )}
          <Space orientation="vertical" size={2}>
            <Typography.Text type="secondary">分配数量</Typography.Text>
            <InputNumber
              stringMode
              min="0.000001"
              value={amount}
              onChange={(value) =>
                setQuantity(value === null ? undefined : String(value))
              }
            />
          </Space>
          <Button
            type="primary"
            disabled={
              !applicable ||
              !amount ||
              (action === "new" ? !(chosenId && chosenSource) : !deviceId)
            }
            onClick={() => action === "new" && configuration.calculation_version === 3 ? setSupplyOpen(true) :
              onApply(
                suggestion,
                action === "new"
                  ? { variantId: chosenId!, sourceId: chosenSource!, quantity: amount }
                  : { existingDeviceId: deviceId!, quantity: amount },
              )
            }
          >
            {action === "new" ? "补入所选配置" : "确认抵扣"}
          </Button>
        </Space>
      ) : null}
    </Card>
  );
}

function scopeLabel(suggestion: Suggestion, configuration: Configuration) {
  if (suggestion.scope === "device") {
    return configuration.devices.find((item) => item.id === suggestion.scope_id)?.name ?? "设备";
  }
  if (suggestion.scope === "system") {
    return configuration.systems.find((item) => item.id === suggestion.scope_id)?.name ?? "系统";
  }
  if (suggestion.scope === "room") {
    return configuration.rooms.find((item) => item.id === suggestion.scope_id)?.name ?? "房间";
  }
  return suggestion.scope === "project" ? "整个项目" : "待确认";
}
