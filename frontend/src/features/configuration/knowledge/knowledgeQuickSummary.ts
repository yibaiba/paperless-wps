import type { Knowledge, Variant } from "../types";

export function knowledgeName(values: Knowledge, variants?: Variant[]) {
  const source = selectedNames(values.selector?.variant_ids ?? [], variants);
  if (values.kind === "suitability") return `${source} · ${values.system} · ${values.role}`;
  if (values.kind === "accessory") return `${source} · 配套 ${values.need_name}`;
  if (values.kind === "combination") return `${source} · 组合要求`;
  return `${source} · 共用部署`;
}

export function knowledgeSummary(values: Knowledge | undefined, variants?: Variant[]) {
  if (!values) return "请先选择产品和关系。";
  const source = selectedNames(values.selector?.variant_ids ?? [], variants);
  if (values.kind === "suitability") {
    const result = values.effect === "deny" ? "不能" : "可以";
    return `${source} ${result}用于 ${values.system || "待选择系统"}，承担${values.role || "待填写角色"}。`;
  }
  if (values.kind === "accessory") {
    const relation = { required: "必须", recommended: "建议", optional: "可以选择" }[
      values.accessory_type
    ];
    const targets = selectedNames(
      values.target_variant_ids ?? [],
      variants,
      "候选型号待确认",
    );
    return `选择 ${source} 后，${relation}搭配“${values.need_name || "待填写配套"}”；可选配置：${targets}。`;
  }
  if (values.kind === "combination") {
    const modes = { exclude: "不能同时选用", require_all: "必须满足全部需求", require_any: "至少满足一项需求" };
    return `${source}：${values.combination ? modes[values.combination.mode] : "待选择组合类型"}，${values.combination?.targets.map(t => t.name).join("、") || "目标待确认"}。`;
  }
  const result = values.effect === "deny" ? "禁止共用" : "满足条件时可以共用";
  return `${source} 在 ${values.shared_roles?.join("、") || "待填写系统角色"} 之间${result}。`;
}

function selectedNames(ids: string[], variants?: Variant[], empty = "待选择产品") {
  const names = ids
    .map((id) => variants?.find((item) => item.id === id))
    .filter((item): item is Variant => Boolean(item))
    .map((item) => `${item.product.model} · ${item.name}`);
  if (!names.length) return empty;
  if (names.length <= 2) return names.join("、");
  return `${names.slice(0, 2).join("、")} 等 ${names.length} 项`;
}
