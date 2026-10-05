"""Physical reservations are separate from role references and procurement supply."""

from decimal import Decimal

from presales.rules.calculation import digest


def reservation_groups(device, consumers, *, assignments, rules, links):
    groups = {}
    for consumer in consumers:
        if consumer["via"] == "direct" and consumer["requirement_id"] in links:
            continue
        mode, key, quantity = reservation(
            consumer, device=device, assignments=assignments, rules=rules
        )
        group = groups.setdefault(key, group_base(device["id"], key, mode, quantity))
        group["consumers"].append(consumer)
        if consumer["demand_id"]:
            group["demand_ids"].add(consumer["demand_id"])
            group["demand_quantities"][consumer["demand_id"]] = str(quantity)
            group["allocation_ids"].update(a["id"] for a in assignments[consumer["demand_id"]])
        group["requirement_ids"].add(logical_id(consumer))
        group["quantity"] = str(max(Decimal(group["quantity"]), quantity))
    represented = {i for group in groups.values() for i in group["demand_ids"]}
    for demand_id in assignments.keys() - represented:
        quantity = sum((Decimal(a["quantity"]) for a in assignments[demand_id]), Decimal(0))
        rule = rules.get(demand_id)
        mode = rule.get("allocation_mode", "consumable") if rule else "unresolved"
        shared = mode == "shareable"
        key = "shared" if shared else "need:" + demand_id
        group = groups.setdefault(
            key, group_base(device["id"], key, "shared" if shared else mode, quantity)
        )
        group["quantity"] = str(max(Decimal(group["quantity"]), quantity))
        group["demand_quantities"][demand_id] = str(quantity)
        group["demand_ids"].add(demand_id)
        group["allocation_ids"].update(a["id"] for a in assignments[demand_id])
    return sorted([finalize_group(g) for g in groups.values()], key=group_order)


def reservation(consumer, *, device, assignments, rules):
    if consumer["via"] == "direct":
        quantity = Decimal(consumer.get("allocated_quantity") or device["quantity"])
        shared = Decimal(device["quantity"]) == 1
        return (
            "shared" if shared else "direct",
            "shared" if shared else "role:" + logical_id(consumer),
            quantity,
        )
    demand_id = consumer["demand_id"]
    quantity = sum((Decimal(a["quantity"]) for a in assignments[demand_id]), Decimal(0))
    shared = rules[demand_id].get("allocation_mode", "consumable") == "shareable"
    return (
        "shared" if shared else "consumable",
        "shared" if shared else "need:" + demand_id,
        quantity,
    )


def logical_id(consumer):
    return consumer.get("allocation_parent_id") or consumer["requirement_id"]


def group_base(device_id, key, mode, quantity):
    return dict(
        id=digest(["device-use", device_id, key]),
        device_id=device_id,
        mode=mode,
        quantity=str(quantity),
        requirement_ids=set(),
        demand_ids=set(),
        allocation_ids=set(),
        consumers=[],
        role_references=[],
        demand_quantities={},
    )


def finalize_group(group):
    mode = group["mode"]
    if mode == "shared" and len(group["requirement_ids"]) == 1 and len(group["demand_ids"]) <= 1:
        mode = "shareable" if group["demand_ids"] else "direct"
    return dict(
        group,
        mode=mode,
        requirement_ids=sorted(group["requirement_ids"]),
        demand_ids=sorted(group["demand_ids"]),
        allocation_ids=sorted(group["allocation_ids"]),
        consumers=sorted(
            group["consumers"], key=lambda c: (logical_id(c), c["via"], c["demand_id"] or "")
        ),
    )


def group_order(group):
    return group["requirement_ids"], group["mode"], group["id"]


def quantity_summary(device, groups):
    independent = sum((Decimal(g["quantity"]) for g in groups if g["mode"] != "shared"), Decimal(0))
    shared = sum((Decimal(g["quantity"]) for g in groups if g["mode"] == "shared"), Decimal(0))
    total = Decimal(device["quantity"])
    used = independent + shared
    return dict(
        total_quantity=str(total),
        independent_quantity=str(independent),
        shared_quantity=str(shared),
        reserved_quantity=str(used),
        unassigned_quantity=str(max(total - used, Decimal(0))),
        overallocated_quantity=str(max(used - total, Decimal(0))),
    )
