import { useState } from "react";
import { Alert, Button, Card, Select, Space, Table, Typography } from "antd";
import type { Checked, Configuration, Suggestion } from "./types";
import { Status, useVariants, variantOptions, sourceOptions } from "./shared";
import { EvidenceDetails } from "./EvidenceDetails";
interface Props {
  checked?: Checked;
  configuration: Configuration;
  stale: boolean;
  busy: boolean;
  onApply: (
    suggestion: Suggestion,
    variantId: string,
    sourceId: string,
  ) => void;
  onCheck: (refresh: boolean) => void;
}
export function ProjectChecks({
  checked,
  configuration,
  stale,
  busy,
  onApply,
  onCheck,
}: Props) {
  const variants = useVariants();
  const [choices, setChoices] = useState<Record<string, string>>({}),
    [sources, setSources] = useState<Record<string, string>>({});
  const names = new Map(configuration.devices.map((d) => [d.id, d.name]));
  return (
    <Card
      title="配置检查与配套"
      extra={
        <Space>
          <Button disabled={busy} onClick={() => onCheck(false)}>
            检查当前配置
          </Button>
          <Button disabled={busy} onClick={() => onCheck(true)}>
            按最新资料重新检查
          </Button>
        </Space>
      }
    >
      <Alert
        type={stale ? "warning" : "info"}
        title={
          stale
            ? "配置已有变化，请重新检查"
            : "通过已知检查不代表整套方案已完成认证"
        }
        description="项目保存保留所用知识版本；按最新资料重新检查会更新本次草稿，保存后才产生新版本。"
      />
      {checked?.version_changes?.length ? (
        <Alert
          type="warning"
          title={`有 ${checked.version_changes.length} 项资料出现新版本，当前结果仍按保存的版本计算`}
          description={checked.version_changes
            .map(
              (v) =>
                `${v.kind === "knowledge" ? "搭配知识" : "产品配置"}：${v.used ?? "未纳入"} → v${v.current}`,
            )
            .join("；")}
        />
      ) : null}
      <Table
        size="small"
        rowKey={(_, i) => String(i)}
        dataSource={checked?.checks}
        columns={[
          {
            title: "对象",
            render: (_, c) =>
              names.get(c.device_id ?? "") ??
              configuration.requirements.find((r) => r.id === c.requirement_id)
                ?.role,
          },
          {
            title: "检查",
            render: (_, c) =>
              ({
                selection: "角色选型",
                compatibility: "适配",
                sharing: "共用部署",
                capacity: "资源容量",
              })[c.kind] ?? c.kind,
          },
          { title: "结果", render: (_, c) => <Status value={c.status} /> },
          {
            title: "说明",
            render: (_, c) =>
              c.message ??
              (c.resource
                ? `${c.resource}：需要 ${c.required} ${c.unit}，容量 ${c.capacity ?? "未知"}`
                : c.evidence?.map((e) => String(e.evidence)).join("；") ||
                  "没有足够的已确认依据"),
          },
        ]}
        expandable={{
          expandedRowRender: (c) => (
            <Space orientation="vertical">
              {c.evidence?.map((e, i) => (
                <div key={i}>
                  <strong>
                    {String(e.name)} · v{String(e.revision)}
                  </strong>
                  <EvidenceDetails evidence={e} />
                </div>
              ))}
            </Space>
          ),
        }}
      />
      <Space orientation="vertical" style={{ width: "100%" }}>
        {checked?.suggestions.map((s) => {
          const candidates = variants.data?.filter((v) =>
            s.rule.target_variant_ids.includes(v.id),
          );
          const chosen =
            choices[s.id] ??
            (candidates?.length === 1 ? candidates[0].id : undefined);
          const variant = candidates?.find((v) => v.id === chosen);
          const source =
            sources[s.id] ??
            (variant?.source_ids.length === 1
              ? variant.source_ids[0]
              : undefined);
          return (
            <Card size="small" key={s.id} title={s.rule.name}>
              <Typography.Paragraph>
                {names.get(s.parent_id)} ·{" "}
                {
                  { required: "必需", recommended: "推荐", optional: "可选" }[
                    s.rule.accessory_type
                  ]
                }{" "}
                · 缺量 {s.missing ?? "条件待确认"}
              </Typography.Paragraph>
              <Space wrap>
                <Select
                  style={{ width: 240 }}
                  placeholder="选择一个配件候选"
                  value={chosen}
                  options={variantOptions(candidates)}
                  onChange={(v) => {
                    setChoices({ ...choices, [s.id]: v });
                    setSources({ ...sources, [s.id]: "" });
                  }}
                />
                <Select
                  style={{ width: 190 }}
                  placeholder="选择资料来源"
                  value={source}
                  options={sourceOptions(variant)}
                  onChange={(id) => setSources({ ...sources, [s.id]: id })}
                />
                <Button
                  disabled={
                    busy ||
                    stale ||
                    s.status !== "pass" ||
                    !Number(s.missing) ||
                    !chosen ||
                    !source
                  }
                  onClick={() => onApply(s, chosen!, source!)}
                >
                  补入所选配件
                </Button>
              </Space>
              <Typography.Paragraph type="secondary">
                {s.rule.evidence}
              </Typography.Paragraph>
            </Card>
          );
        })}
      </Space>
    </Card>
  );
}
