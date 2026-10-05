"""Calculation-only values; serialized views cannot mutate the projection or its input."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

PROJECTION_VERSION = 1


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


def payload(value):
    if isinstance(value, Mapping):
        return {key: payload(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [payload(item) for item in value]
    return value


@dataclass(frozen=True, kw_only=True)
class UsageProjection:
    devices: tuple
    fingerprint: str
    version: int = PROJECTION_VERSION

    def views(self):
        return payload(self.devices)

    def device(self, identity):
        return next(d for d in self.devices if d["device_id"] == identity)

    def available(self, identity, *, demand):
        device = self.device(identity)
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
        return max(min(total - assigned, total - independent), Decimal(0))
