"""Calculation-only values; serialized views cannot mutate the projection or its input."""

import json
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

PROJECTION_VERSION = 1


def freeze(value, *, memo=None):
    memo = {} if memo is None else memo
    if isinstance(value, dict):
        if id(value) in memo:
            return memo[id(value)]
        result = MappingProxyType({key: freeze(item, memo=memo) for key, item in value.items()})
        memo[id(value)] = result
        return result
    if isinstance(value, (list, tuple)):
        if id(value) in memo:
            return memo[id(value)]
        result = tuple(freeze(item, memo=memo) for item in value)
        memo[id(value)] = result
        return result
    return value


@dataclass(frozen=True, kw_only=True)
class UsageProjection:
    devices: tuple
    fingerprint: str
    serialized: str
    version: int = PROJECTION_VERSION
    fulfilled_ids: frozenset = frozenset()

    def views(self):
        return json.loads(self.serialized)

    def device(self, identity):
        return next(d for d in self.devices if d["device_id"] == identity)

    def available(self, identity, *, demand):
        return available_quantity(self.device(identity), demand=demand)

    def referenced_quantity(self, identity, *, demand_ids):
        return sum(
            (
                group_reference_quantity(g, demand_ids=demand_ids)
                for g in self.device(identity)["allocation_groups"]
            ),
            Decimal(0),
        )


def group_reference_quantity(group, *, demand_ids):
    amounts = [
        Decimal(q) for identity, q in group["demand_quantities"].items() if identity in demand_ids
    ]
    return max(amounts, default=Decimal(0))


def available_quantity(device, *, demand):
    if demand["rule"].get("allocation_mode", "consumable") == "consumable":
        return max(Decimal(device["quantity_summary"]["unassigned_quantity"]), Decimal(0))
    assigned = sum(
        (
            Decimal(g["demand_quantities"][demand["id"]])
            for g in device["allocation_groups"]
            if demand["id"] in g["demand_ids"]
        ),
        Decimal(0),
    )
    total = Decimal(device["quantity_summary"]["total_quantity"])
    independent = sum(
        (
            Decimal(g["quantity"])
            for g in device["allocation_groups"]
            if g["mode"] not in {"shared", "shareable"}
        ),
        Decimal(0),
    )
    # A direct reservation of one instance may be explicitly reused by a shared need.
    direct_instance = total == 1 and all(
        g["mode"] in {"direct", "shared", "shareable"} for g in device["allocation_groups"]
    )
    return max(min(total - assigned, total if direct_instance else total - independent), Decimal(0))
