"""Project declared resource policies onto direct and accessory consumers once."""

from ...device_usages import build_device_usages


def resource_usages(data, demands, *, policies, inspections):
    usages = build_device_usages(data, demands)
    rules = {d["id"]: d["rule"] for d in demands}
    for usage in usages:
        usage["consumers"] = [
            enrich(c, policies=policies, inspections=inspections, rules=rules)
            for c in usage["consumers"]
        ]
    return usages


def enrich(consumer, *, policies, inspections, rules):
    rule = rules.get(consumer["demand_id"], {})
    policy = (
        policies.get(consumer["requirement_id"], "unknown")
        if consumer["via"] == "direct"
        else rule.get("resource_policy", "unknown")
    )
    review = inspections.get(consumer["requirement_id"], {})
    conflict = consumer["via"] == "accessory" and rule["need_key"] in review.get("needs", set())
    return dict(
        consumer,
        inspection_policy_conflict=conflict and policy == "not_applicable",
        capacity_expected=bool(consumer["resources"]) or policy != "not_applicable" or conflict,
        resource_policy="required" if conflict else policy,
        allocation_mode=rule.get("allocation_mode", "consumable") if rule else None,
        resource_rule_revision=rule.get("revision"),
        resource_rule_id=rule.get("id"),
    )
