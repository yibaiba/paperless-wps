import type { Attribute, Configuration, Definitions, System } from "../../types";
import type { InspectionMetric } from "../../knowledge/inspectionTypes";

export function systemMetrics(system: System, configuration: Configuration, definitions?: Definitions) {
  const packageValue = definitions?.packages.find((p) => p.id === system.knowledge_package_id);
  const definition = packageValue?.definition ?? definitions?.definitions.find((d) => d.id === system.definition_id);
  const activeRoles = new Set(configuration.requirements.filter((r) => r.system_id === system.id).map((r) => r.role_id));
  const references = definition?.roles.filter((r) => activeRoles.has(r.id)).flatMap((r) => r.inspection_profile ? [r.inspection_profile] : []) ?? [];
  const metrics = new Map<string, InspectionMetric>();
  for (const profile of definition?.inspection_profiles ?? []) {
    if (!references.some((r) => r.id === profile.id && r.revision === profile.revision)) continue;
    for (const metric of profile.metrics) metrics.set(`${metric.input_key}:${metric.input_unit}`, metric);
  }
  return [...metrics.values()];
}

export function initialInputs(existing: Attribute[], metrics: InspectionMetric[]) {
  return {
    values: Object.fromEntries(existing.map((a) => [a.key, metrics.some((m) => m.input_key === a.key && m.input_unit !== a.unit) ? null : a.value])),
    extra: existing.filter((a) => !metrics.some((m) => m.input_key === a.key)),
  };
}

export function combineInputs(metrics: InspectionMetric[], values: Record<string, string | null>, extra: Attribute[]) {
  const inputs: Attribute[] = metrics.map((m) => ({ key: m.input_key, kind: "quantity", value: values[m.input_key] ?? null, unit: m.input_unit }));
  const combined = [...inputs, ...extra];
  if (new Set(combined.map((a) => a.key)).size !== combined.length) throw new Error("输入名称重复，请移除重复参数后再保存");
  return combined;
}
