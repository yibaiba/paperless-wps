"""Project capacity onto the quantities actually reserved for each accessory need."""

from collections import defaultdict
from decimal import Decimal

from ..device_usages import requires_shared_instance, unique_consumers


def allocation_quantities(data):
    quantities = defaultdict(Decimal)
    for allocation in data.get("accessory_allocations", []):
        quantities[allocation["device_id"], allocation["demand_id"]] += Decimal(
            allocation["quantity"]
        )
    return dict(quantities)


def capacity_consumers(usage, *, quantities):
    consumers = [
        dict(c, capacity_expected=bool(c["resources"]) or c["resource_policy"] == "required")
        for c in usage["consumers"]
    ]
    if requires_shared_instance(usage):
        return unique_consumers(consumers)
    by_demand = defaultdict(list)
    for consumer in consumers:
        by_demand[consumer["demand_id"]].append(consumer)
    # All roles served by one need share its assigned quantity, counted once.
    return [
        dict(
            consumer,
            capacity_partition=dict(
                demand_id=demand_id,
                quantity=str(quantities[usage["device_id"], demand_id]),
            ),
        )
        for demand_id, entries in by_demand.items()
        for consumer in unique_consumers(entries)
    ]
