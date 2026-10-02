"""Bind generated accessory roles without replacing explicit user associations."""

from collections import defaultdict
from decimal import Decimal

from ..role_allocations import device_ids
from ..services.manual_edits import marked
from .devices import bind_role
from .questions import question


def fulfillment_demands(data, *, task, demands):
    binding = task["role"]["fulfilled_by"]
    parents = {
        r["id"]
        for r in data["requirements"]
        if r["system_id"] == task["system"]["id"] and r["role_id"] == binding["role_id"]
    }
    return {
        d["id"]
        for d in demands
        if d["need_key"] == binding["need_key"]
        and parents.intersection(d["consumer_requirement_ids"])
    }


def fulfillment_devices(data, *, task, demands):
    matching = fulfillment_demands(data, task=task, demands=demands)
    return {a["device_id"] for a in data["accessory_allocations"] if a["demand_id"] in matching}


def bind_fulfilled_device(data, *, task, identity, demands):
    device = next(d for d in data["devices"] if d["id"] == identity)
    if Decimal(device["quantity"]) == 1:
        return bind_role(data, task["requirement"]["id"], identity)
    matching = fulfillment_demands(data, task=task, demands=demands)
    amounts = defaultdict(Decimal)
    for allocation in data["accessory_allocations"]:
        if allocation["device_id"] == identity and allocation["demand_id"] in matching:
            amounts[allocation["demand_id"]] += Decimal(allocation["quantity"])
    shared = {d["id"] for d in demands if d["rule"]["allocation_mode"] == "shareable"}
    quantity = sum((n for key, n in amounts.items() if key not in shared), Decimal(0))
    quantity += max((n for key, n in amounts.items() if key in shared), default=Decimal(0))
    allocation = dict(
        device_id=identity, quantity=str(quantity), evidence="引用已确认配套分配，不另计采购数量"
    )
    return dict(
        data,
        requirements=[
            dict(r, device_id=None, allocations=[allocation])
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


def bind_fulfilled_roles(data, *, tasks, demands):
    gaps = []
    for task in tasks:
        binding = task["role"].get("fulfilled_by")
        if not binding:
            continue
        devices = fulfillment_devices(data, task=task, demands=demands)
        current = next(r for r in data["requirements"] if r["id"] == task["requirement"]["id"])
        if binding["status"] != "confirmed" or len(devices) != 1:
            gaps.append(
                question(
                    "role_fulfillment_missing",
                    task["requirement"]["id"],
                    "fulfilled_by",
                    "角色与配套的满足依据尚未确认或未形成唯一设备关联",
                    evidence=[binding],
                )
            )
            if not protected_binding(data, current):
                data = bind_role(data, current["id"], None)
            continue
        identity = next(iter(devices))
        manual = marked(data, "requirements", current["id"])
        if set(device_ids(current)) != {identity} and protected_binding(data, current):
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
        data = bind_fulfilled_device(data, task=task, identity=identity, demands=demands)
    return data, gaps
