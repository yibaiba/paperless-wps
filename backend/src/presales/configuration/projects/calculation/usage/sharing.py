"""Check actual reused instances using the pinned sharing knowledge and ZEN."""

from decimal import Decimal

from ....knowledge.evaluator import context_for, scope_matches
from ....knowledge.semantics import evaluate_rules_v3, scope_is_reviewed, shared_roles_match


def sharing_check(data, device, consumers, *, variant, group, decisions=None):
    requirements = {r["id"]: r for r in data["requirements"]}
    systems = {s["id"]: s for s in data["systems"]}
    uses = [
        dict(
            c,
            system_definition_id=systems[c["system_id"]].get("definition_id"),
            knowledge_package_id=systems[c["system_id"]].get("knowledge_package_id"),
            role_id=requirements[c["requirement_id"]].get("role_id"),
        )
        for c in consumers
    ]
    rules = [
        r
        for r in data["knowledge_snapshot"]
        if r["kind"] == "sharing"
        and r["status"] == "confirmed"
        and scope_matches(variant, r["selector"])
        and shared_roles_match(r, uses)
    ]
    results = [
        evaluate_rules_v3(rules, context_for(variant, c["environment"]), decisions=decisions)
        for c in consumers
    ]
    states = {r["status"] for r in results}
    status = "conflict" if "conflict" in states else "unknown" if "unknown" in states else "pass"
    if not rules or not consumers:
        status = "unknown"
    if status == "pass" and any(not scope_is_reviewed(r, variant) for r in rules):
        status = "unknown"
    if Decimal(device["quantity"]) != 1:
        status = "conflict"
    return dict(
        kind="sharing",
        code="shared_instance_conditions",
        device_id=device["id"],
        allocation_group_id=group["id"],
        requirement_ids=group["requirement_ids"],
        demand_ids=group["demand_ids"],
        status=status,
        missing_fields=["sharing_evidence"] if not rules else [],
        message="缺少已确认共用依据" if not rules else "按设备实例核对共享条件",
        evidence=[e for r in results for e in r["evidence"]],
    )
