import { Collapse, Typography } from "antd";
import type { Configuration, Suggestion } from "../types";

export function QuantityEvidence({ suggestion, configuration }: { suggestion: Suggestion; configuration: Configuration }) {
  if (!suggestion.quantity_inputs?.length) return null;
  return <Collapse size="small" items={[{
    key: "inputs", label: `计算输入与依据 · 知识 v${suggestion.rule.revision}`,
    children: suggestion.quantity_inputs.map((input, index) => {
      const device = configuration.devices.find((item) => item.id === input.device_id);
      const role = configuration.requirements.find((item) => item.id === input.requirement_id);
      return <Typography.Paragraph key={`${input.device_id}:${input.requirement_id}:${index}`}>
        {device?.name ?? input.device_id} {role ? ` / ${role.role}` : ""}：
        {input.parameter === "device_quantity" ? "部署数量" : input.parameter} = {input.value ?? "未知"} {input.unit}
        {input.variant_revision ? `；产品配置 v${input.variant_revision}` : ""}
        {input.error ? `；${input.error}` : ""}
      </Typography.Paragraph>;
    }),
  }]} />;
}
