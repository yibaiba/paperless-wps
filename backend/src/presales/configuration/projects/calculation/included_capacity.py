"""Included items remain attached to the host units serving a demand."""

from collections import defaultdict
from decimal import Decimal

from .included_occupancy import IncludedOccupancy


class IncludedCapacity:
    def __init__(self, data, demands):
        self.requirements = {r["id"]: r for r in data["requirements"]}
        self.demands = {d["id"]: d for d in demands}
        self.reserved = defaultdict(Decimal)
        self.scoped = defaultdict(lambda: defaultdict(Decimal))
        self.occupancy = {}
        self.groups = {}
        self.role_scopes = defaultdict(lambda: defaultdict(set))
        for allocation in data.get("included_allocations", []):
            pool = allocation["device_id"], allocation["included_item_id"]
            amount = Decimal(allocation["quantity"])
            self.reserved[pool] += amount
            demand = self.demands.get(allocation["demand_id"])
            scope, _ = self.host_scope(demand, allocation["device_id"])
            self.scoped[pool][scope] += amount
            for role in scope or []:
                self.role_scopes[pool][role].add(scope)

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
            available = self.pool_occupancy(device, fact, scope=scope).available(
                scope, upper_bound=max(min(total - used, scoped_total - scoped_used), Decimal(0))
            )
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

    def conflict(self, device, fact, *, demand):
        if fact.get("quantity") is None:
            return None
        total = Decimal(device["quantity"]) * Decimal(fact["quantity"])
        if self.reserved[device["id"], fact["id"]] > total:
            return "已含数量被重复占用或超出宿主数量，相关抵扣均不计入"
        scope, _ = self.host_scope(demand, device["id"])
        occupancy = self.pool_occupancy(device, fact, scope=scope)
        if scope in occupancy.conflicting:
            return (
                f"本需求及重叠范围已含数量 {occupancy.conflict_capacity}，"
                f"关联抵扣 {occupancy.conflict_quantity}；"
                "不能重复抵扣或转用其他房间、未分配设备的已含内容，相关抵扣不计入"
            )
        return None

    def connected_scope(self, pool, scope):
        if scope is None or None in self.scoped[pool]:
            return None
        if (pool, scope) not in self.groups:
            roles, pending = set(scope), list(scope)
            while pending:
                for other in self.role_scopes[pool].get(pending.pop(), []):
                    added = other - roles
                    roles.update(added)
                    pending.extend(added)
            group = frozenset(roles)
            self.groups[pool, scope] = group
        return self.groups[pool, scope]

    def pool_occupancy(self, device, fact, *, scope):
        pool = device["id"], fact["id"]
        group = self.connected_scope(pool, scope)
        key = pool, group
        if key not in self.occupancy:
            per_unit = Decimal(fact["quantity"])
            capacities = {
                r["id"]: Decimal(r["allocated_quantity"]) * per_unit
                for r in self.requirements.values()
                if r.get("device_id") == device["id"]
                and r.get("allocated_quantity") is not None
                and (group is None or r["id"] in group)
            }
            total = Decimal(device["quantity"]) * per_unit
            self.occupancy[key] = IncludedOccupancy(
                capacities=capacities,
                total=total if group is None else min(total, sum(capacities.values(), Decimal(0))),
                reservations={
                    s: q for s, q in self.scoped[pool].items() if group is None or s <= group
                },
            )
        return self.occupancy[key]
