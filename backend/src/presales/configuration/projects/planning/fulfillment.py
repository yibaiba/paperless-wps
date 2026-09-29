"""Bind generated accessory roles without replacing explicit user associations."""

from ..role_allocations import device_ids
from ..services.manual_edits import marked
from .devices import bind_role
from .questions import question


def bind_fulfilled_roles(data, *, tasks, demands):
    gaps = []
    for task in tasks:
        binding = task["role"].get("fulfilled_by")
        if not binding:
            continue
        parent = next(
            (
                r
                for r in data["requirements"]
                if r["system_id"] == task["system"]["id"] and r["role_id"] == binding["role_id"]
            ),
            None,
        )
        matching = {
            d["id"]
            for d in demands
            if d["need_key"] == binding["need_key"]
            and parent
            and parent["id"] in d["consumer_requirement_ids"]
        }
        devices = {
            a["device_id"] for a in data["accessory_allocations"] if a["demand_id"] in matching
        }
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
            continue
        identity = next(iter(devices))
        current = next(r for r in data["requirements"] if r["id"] == task["requirement"]["id"])
        old_device = next((d for d in data["devices"] if d["id"] == current["device_id"]), None)
        manual = marked(data, "requirements", current["id"])
        if set(device_ids(current)) != {identity} and (
            manual or (old_device and not old_device.get("generated_origin"))
        ):
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
