"""Explicit, non-transferable credits from a host's immutable product snapshot."""

from collections import defaultdict
from decimal import Decimal

from .included_capacity import IncludedCapacity


def included_fulfillment(data, suggestions):
    devices = {d["id"]: d for d in data["devices"]}
    demands = {s["id"]: s for s in suggestions}
    allocations = data.get("included_allocations", [])
    capacity = IncludedCapacity(data, suggestions)
    checks, credits = [], defaultdict(Decimal)
    for allocation in allocations:
        check = allocation_check(allocation, devices=devices, demands=demands, capacity=capacity)
        checks.append(check)
        if check["status"] == "pass":
            credits[allocation["demand_id"]] += Decimal(allocation["quantity"])
    by_demand = defaultdict(list)
    for check in checks:
        by_demand[check["demand_id"]].append(check)
    projected = []
    for demand in suggestions:
        offers = demand_offers(demand, devices=devices, capacity=capacity)
        projected.append(
            dict(
                with_credit(demand, credits[demand["id"]], offers=offers),
                included_allocation_checks=by_demand[demand["id"]],
            )
        )
    return projected, checks


def fact_for(device, identity):
    return next(
        (
            f
            for f in (device.get("variant_snapshot") or {}).get("included_items", [])
            if f["id"] == identity
        ),
        None,
    )


def fact_status(fact, demand, *, device):
    if not fact or fact["status"] == "disabled":
        return "conflict", "已含内容已删除或停用，请核对配置修订"
    if fact["status"] != "confirmed":
        return "unknown", "已含内容尚未确认，不能抵扣"
    if fact.get("quantity") is None or not fact.get("evidence"):
        return "unknown", "已含数量或包含依据缺失"
    if device["id"] not in {i["device_id"] for i in demand.get("quantity_inputs", [])}:
        return "conflict", "该设备不是本需求的宿主，不能转用其已含内容"
    if demand["need_key"] not in fact.get("need_keys", []):
        return "conflict", "包含依据未关联本配套需求"
    if fact.get("variant_id") not in demand["rule"]["target_variant_ids"]:
        return "conflict", "已含配置与配套候选不符"
    if fact["kind"] != demand["rule"]["output_kind"]:
        return "conflict", "已含内容的计量类型与配套需求不符"
    if demand["status"] != "pass" or demand.get("required") is None:
        return demand["status"], "配套条件或数量依据尚未通过，不能抵扣"
    return "pass", "按已确认包含依据抵扣；不新增采购项"


def allocation_check(allocation, *, devices, demands, capacity):
    device = devices.get(allocation["device_id"])
    demand = demands.get(allocation["demand_id"])
    status, message = "conflict", "配套需求或宿主设备已变化，请移除旧抵扣后重新检查"
    if device and demand:
        fact = fact_for(device, allocation["included_item_id"])
        status, message = fact_status(fact, demand, device=device)
        snapshot = device.get("variant_snapshot") or {}
        if (allocation["host_variant_id"], allocation["host_variant_revision"]) != (
            snapshot.get("id"),
            snapshot.get("revision"),
        ):
            status, message = "unknown", "宿主配置修订已变化，请重新核对包含依据并关联"
        elif not demand["selected"]:
            status, message = "conflict", "需求已取消选用，请移除已含抵扣"
        elif fact and fact.get("quantity") is not None:
            conflict = capacity.conflict(device, fact, demand=demand)
            if conflict:
                status, message = "conflict", conflict
    return dict(
        kind="included_allocation",
        status=status,
        message=message,
        allocation_id=allocation["id"],
        demand_id=allocation["demand_id"],
        device_id=allocation["device_id"],
        included_item_id=allocation["included_item_id"],
        **allocation_details(
            allocation, device=device, capacity=capacity, demand=demand, status=status
        ),
        evidence=[
            dict(
                name="已含内容抵扣",
                revision=allocation["host_variant_revision"],
                evidence=allocation["evidence"],
                quantity=allocation["quantity"],
                host_variant_id=allocation["host_variant_id"],
                host_variant_revision=allocation["host_variant_revision"],
            )
        ],
    )


def allocation_details(allocation, *, device, capacity, demand, status):
    snapshot = (device or {}).get("variant_snapshot") or {}
    fact = fact_for(device, allocation["included_item_id"]) if device else None
    counts = capacity.quantities(device, fact, demand=demand) if fact else {}
    return dict(
        counted_quantity=allocation["quantity"] if status == "pass" else "0",
        allocated_quantity=str(
            capacity.reserved[allocation["device_id"], allocation["included_item_id"]]
        ),
        capacity=str(counts["total"]) if counts.get("total") is not None else None,
        scope_capacity=str(counts["scope_total"])
        if counts.get("scope_total") is not None
        else None,
        scope_allocated_quantity=str(counts["scope_allocated"]) if counts else None,
        current_host_variant_id=snapshot.get("id"),
        current_host_variant_revision=snapshot.get("revision"),
        current_evidence=(fact or {}).get("evidence", ""),
        included_name=(fact or {}).get("name", ""),
    )


def demand_offers(demand, *, devices, capacity):
    host_ids = {i["device_id"] for i in demand.get("quantity_inputs", [])}
    offers = []
    for identity in sorted(host_ids):
        device = devices[identity]
        snapshot = device.get("variant_snapshot") or {}
        for fact in snapshot.get("included_items", []):
            if not relevant(fact, demand):
                continue
            status, reason = fact_status(fact, demand, device=device)
            counts = capacity.quantities(device, fact, demand=demand)
            offers.append(
                dict(
                    device_id=identity,
                    included_item_id=fact["id"],
                    name=fact["name"],
                    host_variant_id=snapshot["id"],
                    host_variant_revision=snapshot["revision"],
                    variant_id=fact.get("variant_id"),
                    kind=fact["kind"],
                    status=status,
                    reason=reason,
                    evidence=fact["evidence"],
                    per_unit=fact.get("quantity"),
                    **{k: str(v) if v is not None else None for k, v in counts.items()},
                )
            )
    return offers


def relevant(fact, demand):
    return fact["status"] != "disabled" and (
        demand["need_key"] in fact.get("need_keys", [])
        or fact.get("variant_id") in demand["rule"]["target_variant_ids"]
    )


def with_credit(demand, credit, *, offers):
    assigned = Decimal(demand.get("existing", "0"))
    existing = assigned + credit
    result = dict(
        demand,
        separately_allocated=str(assigned),
        included_quantity=str(credit),
        included_offers=offers,
        existing=str(existing),
    )
    if demand.get("required") is not None:
        required = Decimal(demand["required"])
        result.update(
            missing=str(max(required - existing, Decimal(0))),
            surplus=str(max(existing - required, Decimal(0))),
        )
    return result
