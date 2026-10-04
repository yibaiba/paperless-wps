"""Separate physical deployment totals from explicitly assigned reference-row use."""

from collections import defaultdict
from decimal import Decimal


def mapped_quantity(binding, context, identities):
    configuration = context["configuration"]
    direct = set(binding["device_ids"])
    roles, demands = defaultdict(Decimal), defaultdict(Decimal)
    for role in configuration["requirements"]:
        if role["id"] not in binding["requirement_ids"]:
            continue
        if role.get("device_id"):
            direct.add(role["device_id"])
        for allocation in role.get("allocations", []):
            roles[allocation["device_id"]] += Decimal(allocation["quantity"])
    for allocation in configuration["accessory_allocations"]:
        if allocation["demand_id"] in binding["demand_ids"]:
            demands[allocation["device_id"]] += Decimal(allocation["quantity"])
    total = Decimal(0)
    for identity in identities:
        line = context["lines"].get(identity)
        if not line:
            continue
        quantity = Decimal(line["quantity"])
        if identity in direct or (line.get("kind") == "hardware" and quantity == 1):
            total += quantity
        elif roles[identity] and demands[identity]:
            return None, [
                dict(
                    code="case_overlapping_usage",
                    status="unknown",
                    device_id=identity,
                    message="同一批设备同时按角色和配套映射；请明确这些用量是否重叠，部署列仍展示整批数量",
                )
            ]
        else:
            total += roles[identity] + demands[identity]
    return total, []
