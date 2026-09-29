import type { Configuration, IncludedAllocation, IncludedOffer } from "../types";

/** Keep the allocation identity: the shared edit adapter emits an atomic remove/link batch. */
export function reviewIncludedAllocation(configuration: Configuration, options: {
  allocation: IncludedAllocation; offer: IncludedOffer; quantity: string; evidence: string;
}): Configuration {
  const { allocation, offer, quantity, evidence } = options;
  if (!configuration.included_allocations?.some((a) => a.id === allocation.id)) {
    throw new Error("原抵扣已不存在，请重新打开检查结果");
  }
  if (allocation.device_id !== offer.device_id || allocation.included_item_id !== offer.included_item_id) {
    throw new Error("重新核对必须使用原宿主和包含项；换用其他包含项请重新选择");
  }
  return { ...configuration, included_allocations: configuration.included_allocations.map((a) => a.id === allocation.id ? {
    ...a, quantity, evidence: evidence.trim(), host_variant_id: offer.host_variant_id,
    host_variant_revision: offer.host_variant_revision,
  } : a) };
}
