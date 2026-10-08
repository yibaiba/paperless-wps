"""An explicit recheck exposes usage and check changes without rewriting history."""

from collections import defaultdict
from decimal import Decimal
from itertools import zip_longest

CHECK_IDENTITY_FIELDS = (
    "check_id",
    "kind",
    "code",
    "system_id",
    "room_id",
    "device_id",
    "variant_id",
    "source_id",
    "role_id",
    "profile_id",
    "allocation_group_id",
    "requirement_id",
    "demand_id",
    "resource",
    "rule_id",
    "field",
    "key",
    "scope",
    "scope_id",
    "device_ids",
    "allocation_group_ids",
    "requirement_ids",
    "demand_ids",
)


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
    before = grouped_checks(previous.get("checks", []))
    after = grouped_checks(current.get("checks", []))
    changes = []
    for key in sorted(before.keys() | after.keys()):
        old, new = unmatched_checks(before.get(key, []), after.get(key, []))
        changes.extend(
            dict(previous=previous_check, current=current_check)
            for previous_check, current_check in zip_longest(old, new)
        )
    return changes


def grouped_checks(checks):
    grouped = defaultdict(list)
    for check in checks:
        grouped[check_key(check)].append(check)
    return grouped


def unmatched_checks(previous, current):
    remaining = list(current)
    unmatched = []
    for check in previous:
        if check in remaining:
            remaining.remove(check)
        else:
            unmatched.append(check)
    return unmatched, remaining


def check_key(check):
    identity = (
        (field, frozen(check[field])) for field in CHECK_IDENTITY_FIELDS if field in check
    )
    return str(tuple(identity))


def frozen(value):
    if isinstance(value, dict):
        return tuple(sorted((key, frozen(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(frozen(item) for item in value)
    return value
