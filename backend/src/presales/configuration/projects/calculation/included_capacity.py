"""Included items remain attached to the host units serving a demand."""

from collections import defaultdict
from decimal import Decimal


class IncludedCapacity:
    def __init__(self, data, demands):
        self.requirements = {r["id"]: r for r in data["requirements"]}
        self.demands = {d["id"]: d for d in demands}
        self.reserved = defaultdict(Decimal)
        self.scoped = defaultdict(Decimal)
        for allocation in data.get("included_allocations", []):
            pool = allocation["device_id"], allocation["included_item_id"]
            amount = Decimal(allocation["quantity"])
            self.reserved[pool] += amount
            demand = self.demands.get(allocation["demand_id"])
            scope, _ = self.host_scope(demand, allocation["device_id"])
            self.scoped[pool, scope] += amount

    def host_scope(self, demand, device_id):
        entries = {
            item.get("requirement_id"): self.requirements.get(item.get("requirement_id"), {})
            for item in (demand or {}).get("quantity_inputs", [])
            if item["device_id"] == device_id
        }
        if not entries or any(
            r.get("device_id") != device_id or r.get("allocated_quantity") is None
            for r in entries.values()
        ):
            return None, None
        return frozenset(entries), sum(
            (Decimal(r["allocated_quantity"]) for r in entries.values()), Decimal(0)
        )

    def quantities(self, device, fact, *, demand):
        pool = device["id"], fact["id"]
        used = self.reserved[pool]
        scope, quantity = self.host_scope(demand, device["id"])
        scoped_used = self.scoped[pool, scope] if scope is not None else used
        total = scoped_total = available = None
        if fact.get("quantity") is not None:
            per_unit = Decimal(fact["quantity"])
            host_quantity = Decimal(device["quantity"])
            total = host_quantity * per_unit
            scoped_total = (
                min(quantity, host_quantity) * per_unit if quantity is not None else total
            )
            available = max(min(total - used, scoped_total - scoped_used), Decimal(0))
        return dict(
            total=total,
            allocated=used,
            scope_total=scoped_total,
            scope_allocated=scoped_used,
            available=available,
        )

    def conflict(self, device, fact, *, demand):
        counts = self.quantities(device, fact, demand=demand)
        if counts["total"] is not None and counts["allocated"] > counts["total"]:
            return "已含数量被重复占用或超出宿主数量，相关抵扣均不计入"
        if counts["scope_total"] is not None and counts["scope_allocated"] > counts["scope_total"]:
            return (
                f"本需求范围已含数量 {counts['scope_total']}，"
                f"关联抵扣 {counts['scope_allocated']}；"
                "不能转用其他房间或未分配设备的已含内容，相关抵扣不计入"
            )
        return None
