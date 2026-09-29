"""Compose a role from explicit reusable batches and only the unmet quantity."""

from decimal import Decimal

from ..role_allocations import device_ids
from .devices import bind_role, device_for, put_device, shareable_generated_device
from .questions import question


def role_available(data, device, *, requirement_id):
    occupied = Decimal(0)
    for requirement in data["requirements"]:
        if requirement["id"] == requirement_id:
            continue
        if requirement.get("allocations"):
            occupied += sum(
                (
                    Decimal(a["quantity"])
                    for a in requirement["allocations"]
                    if a["device_id"] == device["id"]
                ),
                Decimal(0),
            )
        elif requirement.get("device_id") == device["id"]:
            occupied += Decimal(device["quantity"])
    # Single physical servers remain subject to the shared-use and capacity checks.
    if Decimal(device["quantity"]) == 1:
        return Decimal(1)
    return max(Decimal(device["quantity"]) - occupied, Decimal(0))


def reusable_batches(context, data, *, requirement, quantity, variant):
    allowed = set(context.preference(requirement["id"]).get("reusable_device_ids", []))
    allowed.update(device_ids(requirement) if requirement.get("allocations") else [])
    own_key = "role:" + requirement["id"]
    result = []
    for device in data["devices"]:
        origin = device.get("generated_origin") or {}
        if origin.get("key") == own_key or device["variant_id"] != variant["id"]:
            continue
        shared = (
            context.deployment == "shared"
            and quantity == 1
            and shareable_generated_device(data, device)
        )
        if device["id"] in allowed or shared:
            result.append(device)
    return result


def bind_allocations(data, requirement, allocations):
    devices = {d["id"]: d for d in data["devices"]}
    if len(allocations) == 1:
        item = allocations[0]
        if Decimal(item["quantity"]) == Decimal(devices[item["device_id"]]["quantity"]):
            return bind_role(data, requirement["id"], item["device_id"])
    return dict(
        data,
        requirements=[
            dict(r, device_id=None, allocations=allocations) if r["id"] == requirement["id"] else r
            for r in data["requirements"]
        ],
    )


def compose_role(context, data, *, task, choice, quantity, reused, evidence, ranking_gap, ranking):
    requirement, variant = task["requirement"], choice["variant"]
    remaining, allocations = quantity, []
    gaps = [ranking_gap] if ranking_gap else []
    for device in reused:
        amount = min(remaining, role_available(data, device, requirement_id=requirement["id"]))
        if amount <= 0:
            continue
        allocations.append(
            dict(
                device_id=device["id"],
                quantity=str(amount),
                evidence="需求明确允许复用，按未占用数量分配",
            )
        )
        remaining -= amount
    result = data
    if remaining:
        result, added, extra = complete_role(
            context, data, task=task, variant=variant, remaining=remaining
        )
        gaps.extend(extra)
        allocations.extend(added)
    if not allocations:
        return result, gaps, []
    result = bind_allocations(result, requirement, allocations)
    return (
        result,
        gaps,
        [
            dict(
                requirement_id=requirement["id"],
                variant_id=variant["id"],
                quantity=str(quantity),
                allocations=allocations,
                reused_quantity=str(quantity - remaining),
                evidence=evidence,
                compatibility=choice["evidence"],
                recommendation=ranking,
            )
        ],
    )


def complete_role(context, data, *, task, variant, remaining):
    requirement, role = task["requirement"], task["role"]
    device, gap = device_for(
        context,
        variant,
        key="role:" + requirement["id"],
        quantity=remaining,
        kind=role.get("output_kind", "hardware"),
        source_id=context.preference(requirement["id"]).get("source_id", ""),
    )
    if gap:
        return data, [], [gap]
    result = put_device(data, device, context=context)
    amount = min(remaining, Decimal(device["quantity"]))
    gaps = []
    if Decimal(device["quantity"]) != remaining:
        gaps.append(
            question(
                "locked_quantity", device["id"], "quantity", "保留人工锁定数量，与计算缺量不同"
            )
        )
    return (
        result,
        [dict(device_id=device["id"], quantity=str(amount), evidence="按角色数量依据补齐剩余需求")],
        gaps,
    )


def candidate_branches(context, data, *, task, quantity, evidence, choices, ranking_gap, ranking):
    for choice in choices:
        batches = reusable_batches(
            context,
            data,
            requirement=task["requirement"],
            quantity=quantity,
            variant=choice["variant"],
        )
        # Try each permitted starting batch, so a conflicting first device cannot hide another.
        orders = [[first, *[d for d in batches if d["id"] != first["id"]]] for first in batches]
        for reused in [*orders, []]:
            yield compose_role(
                context,
                data,
                task=task,
                choice=choice,
                quantity=quantity,
                reused=reused,
                evidence=evidence,
                ranking_gap=ranking_gap,
                ranking=ranking,
            )
