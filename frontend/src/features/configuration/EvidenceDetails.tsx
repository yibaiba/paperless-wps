import { Space, Typography } from "antd";
import { Status } from "./shared";
const fields: Record<string, string> = {
  cpu_arch: "CPU 架构",
  os: "操作系统",
  os_version: "系统版本",
  software_version: "软件版本",
  memory: "内存",
  cores: "CPU 核数",
  capacity: "容量",
  width: "宽度",
  height: "高度",
  depth: "深度",
};
function fieldName(raw: unknown) {
  const [scope, key] = String(raw).split(".");
  return `${scope === "project" ? "需求" : "产品"} · ${fields[key] ?? key}`;
}
function value(raw: unknown) {
  return raw === null || raw === undefined
    ? "未知"
    : Array.isArray(raw)
      ? raw.join(" / ")
      : String(raw);
}
export function EvidenceDetails({
  evidence,
}: {
  evidence: Record<string, unknown>;
}) {
  const conditions = (evidence.conditions ?? []) as {
    field: string;
    result: string;
    operator: string;
    value: unknown;
    minimum: unknown;
    maximum: unknown;
    unit: string;
    actual?: { value: unknown; unit: string };
  }[];
  return (
    <Space orientation="vertical" size={4}>
      <Typography.Text>
        {evidence.effect === "deny" ? "不兼容条件：" : ""}
        {String(evidence.evidence)}
      </Typography.Text>
      {conditions.map((c, i) => (
        <div key={i}>
          <Status value={c.result === "fail" ? "conflict" : c.result} />
          {fieldName(c.field)}：要求{" "}
          {c.operator === "range"
            ? `${value(c.minimum)} 至 ${value(c.maximum)}`
            : value(c.value)}{" "}
          {c.unit}；当前 {value(c.actual?.value)} {c.actual?.unit}
        </div>
      ))}
    </Space>
  );
}
