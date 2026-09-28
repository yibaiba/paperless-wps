import { Alert, Button, Card, Collapse, Space, Table } from "antd";
import type { ApplyChoice, Checked, Configuration, Suggestion } from "./types";
import { Status, useVariants } from "./shared";
import { checkLabels } from "./projects/checkLabels";
import { EvidenceDetails } from "./EvidenceDetails";
import { AccessorySuggestionCard } from "./AccessorySuggestionCard";
interface Props {
  checked?: Checked;
  configuration: Configuration;
  stale: boolean;
  busy: boolean;
  onApply: (suggestion: Suggestion, choice: ApplyChoice) => void;
  onCheck: (refresh: boolean) => void;
  onChoice?: (demandId: string, selected: boolean) => void;
  section?: "all" | "accessories" | "checks";
}
export function ProjectChecks({
  checked,
  configuration,
  stale,
  busy,
  onApply,
  onCheck,
  onChoice,
  section = "all",
}: Props) {
  const variants = useVariants();
  const names = new Map(configuration.devices.map((d) => [d.id, d.name]));
  return (
    <Card
      title={section === "accessories" ? "配套选择" : "配置检查"}
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
        description="项目保存保留所用知识版本；按最新资料重新检查会先展示升级预览，应用并保存后才产生新版本。"
      />
      {checked?.version_changes?.length ? (
        <Alert
          type="warning"
          title={`有 ${checked.version_changes.length} 项资料出现新版本，当前结果仍按保存的版本计算`}
          description={<Collapse items={[{ key: "versions", label: "展开查看资料版本差异", children: checked.version_changes
            .map(
              (v) =>
                `${
                  v.kind === "knowledge"
                    ? "搭配知识"
                    : v.kind === "calculation"
                      ? "计算方式"
                      : v.kind === "system_definition"
                        ? "系统角色定义"
                        : v.kind === "knowledge_package"
                          ? "系统知识包"
                      : v.kind === "inspection_profile" ? "用途检查定义" : "产品配置"
                }：${v.used ?? "未纳入"} → v${v.current}`,
            )
            .join("；") }]} />}
        />
      ) : null}
      {section !== "accessories" ? <Table
        size="small"
        rowKey={(item) =>
          [
            item.kind,
            item.system_id,
            item.role_id,
            item.device_id,
            item.requirement_id,
            item.demand_id,
            item.resource,
            item.message,
          ].join(":")
        }
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
              c.responsibility === "project" ? checkLabels.project_configuration : checkLabels[c.kind] ?? c.kind,
          },
          { title: "结果", render: (_, c) => <Status value={c.status} /> },
          {
            title: "说明",
            render: (_, c) =>
              c.message ??
              (c.resource
                ? `${c.resource}：需要 ${c.required} ${c.unit}，容量 ${c.capacity ?? "未知"}`
                : c.evidence?.length ? "展开查看条件与来源依据" : "没有足够的已确认依据"),
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
      /> : null}
      {section !== "checks" ? <Space orientation="vertical" style={{ width: "100%" }}>
        {checked?.suggestions.map((suggestion) => (
          <AccessorySuggestionCard
            key={suggestion.id}
            suggestion={suggestion}
            configuration={configuration}
            variants={variants.data}
            busy={busy}
            stale={stale}
            onApply={onApply}
            onChoice={onChoice}
          />
        ))}
      </Space> : null}
    </Card>
  );
}
