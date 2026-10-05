"""Bind generated accessory roles without replacing explicit user associations."""

from decimal import Decimal

from ..calculation.usage.bindings import role_need_ids
from ..role_allocations import device_ids
from ..services.manual_edits import marked
from .devices import bind_role
from .questions import question
from .usage import branch_usage


def fulfillment_demands(data, *, task, demands):
    binding = task["role"]["fulfilled_by"]
    return role_need_ids(
        data,
        system_id=task["system"]["id"],
        role_id=binding["role_id"],
        need_key=binding["need_key"],
        demands=demands,
    )


def fulfillment_devices(data, *, task, demands):
    matching = fulfillment_demands(data, task=task, demands=demands)
    return {a["device_id"] for a in data["accessory_allocations"] if a["demand_id"] in matching}


def bind_fulfilled_device(data, *, task, identities, projection, demands):
    if len(identities) == 1:
        identity = next(iter(identities))
        if Decimal(projection.device(identity)["quantity_summary"]["total_quantity"]) == 1:
            return bind_role(data, task["requirement"]["id"], identity)
    matching = fulfillment_demands(data, task=task, demands=demands)
    allocations = [
        dict(
            device_id=identity,
            quantity=str(projection.referenced_quantity(identity, demand_ids=matching)),
            evidence="引用已确认配套分配，不另计采购数量",
        )
        for identity in sorted(identities)
    ]
    return dict(
        data,
        requirements=[
            dict(r, device_id=None, allocations=allocations)
            if r["id"] == task["requirement"]["id"]
            else r
            for r in data["requirements"]
        ],
    )


def protected_binding(data, requirement):
    identities = set(device_ids(requirement))
    return marked(data, "requirements", requirement["id"]) or any(
        d["id"] in identities and not d.get("generated_origin") for d in data["devices"]
    )


def bind_fulfilled_roles(data, *, tasks, demands, context):
    gaps = []
    projection = branch_usage(context, data, demands=demands)
    for task in tasks:
        binding = task["role"].get("fulfilled_by")
        if not binding:
            continue
        devices = fulfillment_devices(data, task=task, demands=demands)
        current = next(r for r in data["requirements"] if r["id"] == task["requirement"]["id"])
        if binding["status"] != "confirmed" or not devices:
            gaps.append(
                question(
                    "role_fulfillment_missing",
                    task["requirement"]["id"],
                    "fulfilled_by",
                    "角色与配套的满足依据尚未确认或未形成设备分配关联",
                    evidence=[binding],
                )
            )
            if not protected_binding(data, current):
                data = bind_role(data, current["id"], None)
            continue
        manual = marked(data, "requirements", current["id"])
        if set(device_ids(current)) != devices and protected_binding(data, current):
            gaps.append(
                dict(
                    question(
                        "manual_fulfillment_conflict",
                        current["id"],
                        "device_id",
                        "保留人工关联设备；与生成配套关联不一致",
                        recipient="customer",
                    ),
                    status="conflict",
                )
            )
            continue
        if manual:
            continue
        data = bind_fulfilled_device(
            data, task=task, identities=devices, projection=projection, demands=demands
        )
    return data, gaps
