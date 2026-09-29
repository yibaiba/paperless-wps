"""Allocation choices preserve manual locks and explicitly reusable stock."""

from decimal import Decimal

from .devices import allocation, available, device_for, put_device
from .questions import question


def locked_accessory(context, data, demand):
    key = "accessory:" + demand["id"]
    previous = next(
        (d for d in data["devices"] if (d.get("generated_origin") or {}).get("key") == key), None
    )
    if not previous or not previous["generated_origin"]["variant_locked"]:
        return None
    needed = Decimal(demand["missing"])
    amount = min(needed, Decimal(previous["quantity"]))
    questions = []
    if previous["variant_id"] not in demand["rule"]["target_variant_ids"]:
        questions.append(
            dict(
                question(
                    "locked_accessory_conflict",
                    previous["id"],
                    "variant_id",
                    "保留人工选择的配套型号，但不在当前需求允许的候选范围内",
                    recipient="customer",
                ),
                status="conflict",
            )
        )
    if amount < needed:
        questions.append(
            question(
                "locked_accessory_quantity",
                previous["id"],
                "quantity",
                f"人工配套数量不足，仍缺 {needed - amount}；保留人工设备并等待确认",
                recipient="customer",
            )
        )
    result = allocation(data, demand, previous["id"], quantity=amount) if amount else data
    return (
        result,
        questions,
        dict(
            demand_id=demand["id"],
            device_id=previous["id"],
            reason="保留人工配套型号及数量",
            evidence=demand["explanation"],
        ),
    )


def new_accessory(context, data, *, variant, demand, needed, gaps, ranking):
    device, source_gap = device_for(
        context,
        variant,
        key="accessory:" + demand["id"],
        quantity=needed,
        kind=demand["rule"]["output_kind"],
    )
    if source_gap:
        return data, [source_gap], dict(demand_id=demand["id"], variant_id=variant["id"])
    device["origin_suggestion"] = demand["id"]
    actual = min(needed, Decimal(device["quantity"]))
    result = put_device(data, device, context=context)
    if actual:
        result = allocation(result, demand, device["id"], quantity=actual)
    if actual < needed:
        gaps = [
            *gaps,
            question(
                "locked_accessory_quantity",
                device["id"],
                "quantity",
                f"保留人工锁定数量，配套仍缺 {needed - actual}",
                recipient="customer",
            ),
        ]
    return (
        result,
        gaps,
        dict(
            demand_id=demand["id"],
            device_id=device["id"],
            variant_id=variant["id"],
            evidence=demand["explanation"],
            recommendation=ranking,
        ),
    )


def reusable_accessory(context, data, *, variant, demand, demands, allowed, gaps, ranking):
    remaining = Decimal(demand["missing"])
    result = data
    used = []
    for existing in data["devices"]:
        if existing["variant_id"] != variant["id"]:
            continue
        shared = (
            context.deployment == "shared"
            and demand["rule"]["allocation_mode"] == "shareable"
            and Decimal(existing["quantity"]) == 1
        )
        if existing["id"] not in allowed and not shared:
            continue
        amount = min(remaining, available(result, existing, demand, demands))
        if amount <= 0:
            continue
        result = allocation(result, demand, existing["id"], quantity=amount)
        remaining -= amount
        used.append(existing["id"])
        if remaining == 0:
            break
    if not used:
        return None
    if remaining:
        return new_accessory(
            context,
            result,
            variant=variant,
            demand=demand,
            needed=remaining,
            gaps=gaps,
            ranking=ranking,
        )
    return (
        result,
        gaps,
        dict(
            demand_id=demand["id"],
            device_id=used[0],
            device_ids=used,
            recommendation=ranking,
            reason="明确允许的已有设备先抵扣，余量另行生成；共享仍须核对依据与容量",
            evidence=demand["explanation"],
        ),
    )
