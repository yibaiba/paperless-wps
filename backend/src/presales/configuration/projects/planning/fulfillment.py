"""Bind generated accessory roles without replacing explicit user associations."""

from ..role_allocations import device_ids
from ..services.manual_edits import marked
from .devices import bind_role
from .questions import question


def fulfillment_devices(data, *, task, demands):
    binding = task["role"]["fulfilled_by"]
    parents = {
        r["id"]
        for r in data["requirements"]
        if r["system_id"] == task["system"]["id"] and r["role_id"] == binding["role_id"]
    }
    matching = {
        d["id"]
        for d in demands
        if d["need_key"] == binding["need_key"]
        and parents.intersection(d["consumer_requirement_ids"])
    }
    return {a["device_id"] for a in data["accessory_allocations"] if a["demand_id"] in matching}


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
        data = bind_role(data, task["requirement"]["id"], identity)
    return data, gaps
