"""Included items remain attached to the host units serving a demand."""

from collections import defaultdict
from decimal import Decimal


class IncludedCapacity:
    def __init__(self, data, demands):
        self.requirements = {r["id"]: r for r in data["requirements"]}
        self.demands = {d["id"]: d for d in demands}
        self.reserved = defaultdict(Decimal)
        self.scoped = defaultdict(lambda: defaultdict(Decimal))
        self.host_limits = defaultdict(dict)
        for demand in demands:
            for device_id in {i["device_id"] for i in demand.get("quantity_inputs", [])}:
                scope, quantity = self.host_scope(demand, device_id)
                if scope is not None:
                    self.host_limits[device_id][scope] = quantity
        for allocation in data.get("included_allocations", []):
            pool = allocation["device_id"], allocation["included_item_id"]
            amount = Decimal(allocation["quantity"])
            self.reserved[pool] += amount
            demand = self.demands.get(allocation["demand_id"])
            scope, _ = self.host_scope(demand, allocation["device_id"])
            self.scoped[pool][scope] += amount

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
        scoped_used = self.scope_usage(pool, scope) if scope is not None else used
        total = scoped_total = available = None
        if fact.get("quantity") is not None:
            per_unit = Decimal(fact["quantity"])
            host_quantity = Decimal(device["quantity"])
            total = host_quantity * per_unit
            scoped_total = (
                min(quantity, host_quantity) * per_unit if quantity is not None else total
            )
            # A smaller role scope also consumes its containing system/room scope.
            remaining = [total - used, scoped_total - scoped_used]
            remaining.extend(
                c["total"] - c["allocated"] for c in self.constraints(device, fact, scope)
            )
            available = max(min(remaining), Decimal(0))
        return dict(
            total=total,
            allocated=used,
            scope_total=scoped_total,
            scope_allocated=scoped_used,
            available=available,
        )

    def scope_usage(self, pool, scope):
        return sum(
            (
                amount
                for current, amount in self.scoped.get(pool, {}).items()
                if current is not None and current <= scope
            ),
            Decimal(0),
        )

    def constraints(self, device, fact, scope):
        if scope is None or fact.get("quantity") is None:
            return []
        limits = self.host_limits.get(device["id"], {})
        containing = sorted((s for s in limits if scope <= s), key=lambda s: (len(s), sorted(s)))
        return [
            dict(
                total=min(limits[s], Decimal(device["quantity"])) * Decimal(fact["quantity"]),
                allocated=self.scope_usage((device["id"], fact["id"]), s),
            )
            for s in containing
        ]

    def conflict(self, device, fact, *, demand):
        counts = self.quantities(device, fact, demand=demand)
        if counts["total"] is not None and counts["allocated"] > counts["total"]:
            return "已含数量被重复占用或超出宿主数量，相关抵扣均不计入"
        scope, _ = self.host_scope(demand, device["id"])
        for limit in self.constraints(device, fact, scope):
            if limit["allocated"] > limit["total"]:
                return (
                    f"本需求及其重叠范围已含数量 {limit['total']}，"
                    f"关联抵扣 {limit['allocated']}；"
                    "不能重复抵扣或转用其他房间、未分配设备的已含内容，相关抵扣不计入"
                )
        return None
