"""Separate unreviewed capacity applicability from missing resource quantities."""


def resource_policy_checks(usage):
    unresolved = [
        c for c in usage["consumers"] if c["resource_policy"] == "unknown" and not c["resources"]
    ]
    if not unresolved:
        return []
    demand_ids = list(dict.fromkeys(c["demand_id"] for c in unresolved if c["demand_id"]))
    rule_ids = list(
        dict.fromkeys(c["resource_rule_id"] for c in unresolved if c.get("resource_rule_id"))
    )
    return [
        dict(
            kind="resource_policy",
            status="unknown",
            device_id=usage["device_id"],
            requirement_ids=list(dict.fromkeys(c["requirement_id"] for c in unresolved)),
            demand_id=demand_ids[0] if len(demand_ids) == 1 else None,
            demand_ids=demand_ids,
            rule_id=rule_ids[0] if len(rule_ids) == 1 else None,
            rule_revision=next(
                (
                    c.get("resource_rule_revision")
                    for c in unresolved
                    if c.get("resource_rule_id") == rule_ids[0]
                ),
                None,
            )
            if len(rule_ids) == 1
            else None,
            message="维护者尚未确认本用途是否需要容量检查；请依据资料明确检查指标或不适用，"
            "不要为消除提示填写虚构资源需求",
        )
    ]
