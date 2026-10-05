"""Quantities, sharing and capacity all consume the same reservation groups."""

from decimal import Decimal

from ...device_usages import capacity_checks, unique_consumers
from ..resource_review import resource_policy_checks
from .sharing import sharing_check


def usage_checks(data, usages, *, variants, decisions=None):
    devices = {d["id"]: d for d in data["devices"]}
    checks = []
    for usage in usages:
        device = devices[usage["device_id"]]
        checks.extend(usage["allocation_checks"])
        checks.extend(quantity_checks(usage))
        checks.extend(resource_policy_checks(usage))
        checks.extend(inspection_conflicts(usage))
        if usage["missing_information"]:
            checks.append(
                dict(
                    kind="accessory_allocation",
                    status="unknown",
                    code="allocation_consumer_missing",
                    device_id=device["id"],
                    allocation_group_ids=[g["id"] for g in usage["allocation_groups"]],
                    missing_fields=["consumer_requirement_ids"],
                    message="；".join(usage["missing_information"]),
                )
            )
        consumers = capacity_consumers(usage)
        metrics = capacity_checks(
            device, consumers, variant=variants[device["id"]], usage=usage, decisions=decisions
        )
        checks.extend(metrics)
        for group in usage["allocation_groups"]:
            if group["mode"] == "shared":
                checks.append(
                    sharing_check(
                        data,
                        device,
                        unique_consumers(group["consumers"]),
                        variant=variants[device["id"]],
                        group=group,
                        decisions=decisions,
                    )
                )
    return checks


def quantity_checks(usage):
    summary = usage["quantity_summary"]
    if Decimal(summary["overallocated_quantity"]) <= 0:
        return []
    groups = usage["allocation_groups"]
    return [
        dict(
            kind="accessory_allocation"
            if any(g["demand_ids"] for g in groups)
            else "role_allocation",
            status="conflict",
            code="device_quantity_overallocated",
            device_id=usage["device_id"],
            allocation_group_ids=[g["id"] for g in groups],
            requirement_ids=sorted({i for g in groups for i in g["requirement_ids"]}),
            demand_ids=sorted({i for g in groups for i in g["demand_ids"]}),
            allocated=summary["reserved_quantity"],
            available=summary["total_quantity"],
            excess=summary["overallocated_quantity"],
            missing_fields=["allocations", "quantity"],
            message=(
                f"用途分配合计 {summary['reserved_quantity']}，"
                f"超过部署数量 {summary['total_quantity']}"
            ),
        )
    ]


def capacity_consumers(usage):
    return [
        dict(
            c,
            capacity_expected=bool(c["resources"]) or c["resource_policy"] == "required",
            capacity_partition=dict(
                group_id=g["id"],
                quantity=g["quantity"],
                demand_ids=g["demand_ids"],
                demand_id=g["demand_ids"][0] if len(g["demand_ids"]) == 1 else None,
            ),
        )
        for g in usage["allocation_groups"]
        for c in unique_consumers(g["consumers"])
    ]


def inspection_conflicts(usage):
    return [
        dict(
            kind="inspection",
            status="conflict",
            device_id=usage["device_id"],
            requirement_id=c["requirement_id"],
            rule_id=c["resource_rule_id"],
            rule_revision=c["resource_rule_revision"],
            allocation_group_ids=c["group_ids"],
            message="配套关系标记无需容量检查，但用途检查指定了资源需求，请核对依据",
        )
        for c in usage["consumers"]
        if c.get("inspection_policy_conflict")
    ]
