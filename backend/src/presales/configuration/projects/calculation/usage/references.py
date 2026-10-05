"""Role aliases name their backing reservations; they never create new reservations."""

from decimal import Decimal

from .groups import logical_id
from .models import group_reference_quantity


def attach_references(groups, consumers, *, links, device):
    references = []
    for consumer in consumers:
        matches = links.get(consumer["requirement_id"])
        if consumer["via"] != "direct" or not matches:
            continue
        demand_ids = {link["demand_id"] for link in matches}
        targets = [g for g in groups if demand_ids.intersection(g["demand_ids"])]
        reference = dict(
            requirement_id=logical_id(consumer),
            quantity=str(consumer.get("allocated_quantity") or device["quantity"]),
            group_ids=[g["id"] for g in targets],
            group_quantities={
                g["id"]: str(group_reference_quantity(g, demand_ids=demand_ids)) for g in targets
            },
            demand_ids=sorted(demand_ids),
            fulfilled_by_requirement_ids=sorted({link["requirement_id"] for link in matches}),
            resources=consumer["resources"],
        )
        references.append(reference)
        for group in targets:
            group["role_references"].append(reference)
            group["requirement_ids"] = sorted(
                set(group["requirement_ids"]) | {logical_id(consumer)}
            )
            # A resource cannot be duplicated over independent groups without a stated split.
            if len(targets) == 1:
                parents = reference["fulfilled_by_requirement_ids"]
                group["consumers"].append(
                    dict(
                        consumer,
                        fulfilled_by_requirement_id=parents[0] if len(parents) == 1 else None,
                        fulfilled_by_requirement_ids=parents,
                        fulfilled_by_demand_ids=reference["demand_ids"],
                    )
                )
    return references


def reference_checks(references, groups, *, device_id):
    indexed = {g["id"]: g for g in groups}
    checks = []
    for reference in references:
        targets = [indexed[i] for i in reference["group_ids"]]
        quantity = sum(
            (Decimal(reference["group_quantities"][g["id"]]) for g in targets), Decimal(0)
        )
        base = dict(
            device_id=device_id,
            requirement_id=reference["requirement_id"],
            allocation_group_ids=reference["group_ids"],
            demand_ids=reference["demand_ids"],
        )
        if Decimal(reference["quantity"]) > quantity:
            checks.append(
                dict(
                    base,
                    kind="role_allocation",
                    status="conflict",
                    code="role_reference_overallocated",
                    required=str(quantity),
                    allocated=reference["quantity"],
                    message="角色引用数量超过其实际配套分配，请核对引用范围",
                )
            )
        if len(targets) > 1 and reference["resources"]:
            checks.append(
                dict(
                    base,
                    kind="capacity",
                    status="unknown",
                    code="resource_split_missing",
                    missing_fields=["resources", "allocation_scope"],
                    message="角色资源涉及多个独立分配组，缺少明确分摊依据",
                )
            )
    return checks
