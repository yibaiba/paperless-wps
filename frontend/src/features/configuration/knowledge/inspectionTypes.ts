import type { Authored } from "../types";
export interface InspectionMetric {
  key: string; label: string; input_key: string; input_label: string; input_unit: string; unit: string;
  aggregation: "sum" | "max"; capacity_basis: "deployment" | "unit"; factor: string;
  applies_to: "selected_device" | "accessory"; target_need_key: string;
}
export interface InspectionProfile extends Authored {
  id: string; revision: number; name: string; status: "draft" | "confirmed" | "disabled";
  selected_device_policy: "unknown" | "required" | "not_applicable";
  metrics: InspectionMetric[];
}
