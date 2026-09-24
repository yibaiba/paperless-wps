from collections import defaultdict
from decimal import Decimal


def prune_stale_allocations(data, demands):
    valid_demands = {item["id"] for item in demands}
    allocations = data.get("accessory_allocations", [])
    removed = [item for item in allocations if item["demand_id"] not in valid_demands]
    if not removed:
        return []
    data["accessory_allocations"] = [
        item for item in allocations if item["demand_id"] in valid_demands
    ]
    return [
        dict(
            kind="accessory_allocation_cleanup",
            demand_id=item["demand_id"],
            device_id=item["device_id"],
            status="pass",
            message="原配套需求已不存在，已移除对应分配",
        )
        for item in removed
    ]


def accessory_allocation_checks(data, demands):
    by_id = {item["id"]: item for item in demands}
    devices = {item["id"]: item for item in data["devices"]}
    consumptive = defaultdict(Decimal)
    checks = []
    for allocation in data.get("accessory_allocations", []):
        demand = by_id.get(allocation["demand_id"])
        device = devices.get(allocation["device_id"])
        if demand is None:
            checks.append(allocation_check(allocation, "unknown", "配套需求已变化，请重新关联"))
            continue
        if device is None or device["variant_id"] not in demand["rule"]["target_variant_ids"]:
            checks.append(allocation_check(allocation, "conflict", "分配设备不属于候选配置"))
            continue
        if demand["rule"].get("allocation_mode", "consumable") == "consumable":
            consumptive[device["id"]] += Decimal(allocation["quantity"])
    checks.extend(over_allocated_checks(consumptive, devices))
    return checks


def over_allocated_checks(consumptive, devices):
    checks = []
    for device_id, used in consumptive.items():
        available = Decimal(devices[device_id]["quantity"])
        if used > available:
            checks.append(
                dict(
                    kind="accessory_allocation",
                    device_id=device_id,
                    status="conflict",
                    message=f"配套分配合计 {used}，超过设备数量 {available}",
                )
            )
    return checks


def allocation_check(allocation, status, message):
    return dict(
        kind="accessory_allocation",
        device_id=allocation["device_id"],
        demand_id=allocation["demand_id"],
        status=status,
        message=message,
    )
