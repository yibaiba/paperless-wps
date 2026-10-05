"""An explicit recheck exposes usage and check changes without rewriting history."""

from decimal import Decimal


def usage_differences(previous, current):
    before = {u["device_id"]: u for u in previous.get("device_usages", [])}
    after = {u["device_id"]: u for u in current.get("device_usages", [])}
    return [
        dict(
            device_id=identity,
            previous=usage_state(before.get(identity)),
            current=usage_state(after.get(identity)),
        )
        for identity in sorted(before.keys() | after.keys())
        if usage_state(before.get(identity)) != usage_state(after.get(identity))
    ]


def usage_state(usage):
    if not usage:
        return None
    summary = usage.get("quantity_summary")
    return dict(
        quantity_summary={k: str(Decimal(v).normalize()) for k, v in summary.items()}
        if summary
        else None,
        groups=sorted(
            [
                dict(
                    id=g["id"],
                    mode=g["mode"],
                    quantity=str(Decimal(g["quantity"]).normalize()),
                    requirement_ids=g["requirement_ids"],
                    demand_ids=g["demand_ids"],
                )
                for g in usage.get("allocation_groups", [])
            ],
            key=lambda g: g["id"],
        ),
        role_references=usage.get("role_references", []),
        resources=usage.get("resource_calculations", []),
    )


def check_differences(previous, current):
    before = {check_key(c): c for c in previous.get("checks", [])}
    after = {check_key(c): c for c in current.get("checks", [])}
    return [
        dict(previous=before.get(k), current=after.get(k))
        for k in sorted(before.keys() | after.keys())
        if before.get(k) != after.get(k)
    ]


def check_key(check):
    return str(
        (
            check["kind"],
            check.get("code"),
            check.get("device_id"),
            check.get("allocation_group_id"),
            check.get("requirement_id"),
            tuple(check.get("requirement_ids", [])),
            check.get("demand_id"),
            check.get("resource"),
            check.get("rule_id"),
        )
    )
