"""Aggregate declared demands, preserving calculation basis and inspection evidence."""

from collections import defaultdict
from decimal import Decimal, InvalidOperation


def metric_checks(device, consumers, *, variant, decisions=None, partitioned=False):
    groups = defaultdict(list)
    for consumer in consumers:
        for resource in consumer["resources"]:
            groups[resource["key"]].append(
                dict(
                    resource,
                    requirement_id=consumer["requirement_id"],
                    allocated_quantity=consumer.get("allocated_quantity"),
                )
            )
    attributes = {a["key"]: a for a in variant["attributes"]}
    return [
        check
        for key, items in groups.items()
        for check in group_results(
            device,
            items,
            attribute=attributes.get(key),
            decisions=decisions,
            partitioned=partitioned,
        )
    ]


def resource_bases(items):
    return {
        (i["unit"], i.get("aggregation", "sum"), i.get("capacity_basis", "deployment"))
        for i in items
    }


def group_results(device, items, *, attribute, decisions, partitioned):
    bases = resource_bases(items)
    if not partitioned or len(bases) != 1 or items[0].get("capacity_basis") != "unit":
        return [metric_result(device, items, attribute=attribute, decisions=decisions)]
    # Independently allocated units cannot borrow another role's spare capacity.
    by_requirement = defaultdict(list)
    for item in items:
        by_requirement[item["requirement_id"]].append(item)
    checks = []
    for resources in by_requirement.values():
        quantity = min(Decimal(resources[0]["allocated_quantity"]), Decimal(device["quantity"]))
        checks.append(
            metric_result(
                dict(device, quantity=str(quantity)),
                resources,
                attribute=attribute,
                decisions=decisions,
            )
        )
    return checks


def metric_result(device, items, *, attribute, decisions=None):
    first = items[0]
    check = dict(
        kind="capacity",
        device_id=device["id"],
        resource=first["key"],
        unit=first["unit"],
        requirement_ids=list(dict.fromkeys(i["requirement_id"] for i in items)),
        evidence=[i["inspection_evidence"] for i in items if i.get("inspection_evidence")],
    )
    bases = resource_bases(items)
    if len(bases) != 1:
        return dict(
            check,
            status="conflict",
            message="同一资源的单位、合计方式或容量范围不一致，请核对用途检查",
        )
    unit, aggregation, basis = next(iter(bases))
    values = [Decimal(i["amount"]) for i in items]
    required = max(values) if aggregation == "max" else sum(values, Decimal(0))
    capacity = known_capacity(attribute, unit)
    if capacity is not None and basis == "unit":
        capacity *= Decimal(str(device["quantity"]))
    status = (
        decisions.capacity(required=required, capacity=capacity)
        if decisions
        else "unknown"
        if capacity is None
        else "pass"
        if capacity >= required
        else "conflict"
    )
    return dict(
        check,
        status=status,
        required=str(required),
        capacity=str(capacity) if capacity is not None else None,
        aggregation=aggregation,
        capacity_basis=basis,
        message=f"缺少同单位产品容量：{first['key']}（{unit}）" if capacity is None else None,
    )


def known_capacity(attribute, unit):
    if (
        not attribute
        or attribute["kind"] not in {"number", "quantity"}
        or attribute["unit"] != unit
    ):
        return None
    try:
        capacity = Decimal(str(attribute["value"]))
    except InvalidOperation:
        return None
    return capacity if capacity.is_finite() and capacity >= 0 else None
