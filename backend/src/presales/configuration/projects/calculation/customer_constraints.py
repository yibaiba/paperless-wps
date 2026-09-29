"""Customer constraints shared by full checks, quote edits and generated proposals."""

from decimal import Decimal

from ..role_allocations import device_ids
from .interpretations import interpretation_checks

CONSTRAINT_KINDS = frozenset({"product_constraint", "budget", "interpretation"})


def with_customer_constraints(checked):
    data = checked["configuration"]
    retained = [c for c in checked["checks"] if c["kind"] not in CONSTRAINT_KINDS]
    return dict(
        checked,
        checks=[
            *retained,
            *product_constraints(data),
            *budget_checks(data, checked),
            *interpretation_checks(data),
        ],
    )


def product_constraints(data):
    devices = {d["id"]: d for d in data["devices"]}
    requirements = {r["id"]: r for r in data["requirements"]}
    checks = []
    for preference in data.get("generation", {}).get("preferences", []):
        requirement = requirements.get(preference["requirement_id"])
        if requirement is None:
            raise ValueError("客户选型要求引用的角色不存在，请重新关联需求")
        chosen = {devices[identity]["variant_id"] for identity in device_ids(requirement)}
        excluded = chosen & set(preference["excluded_variant_ids"])
        mismatch = preference["required_variant_id"] and chosen - {
            preference["required_variant_id"]
        }
        if excluded or mismatch:
            checks.append(
                dict(
                    kind="product_constraint",
                    code="product_constraint_conflict",
                    status="conflict",
                    requirement_id=requirement["id"],
                    system_id=requirement["system_id"],
                    role_id=requirement.get("role_id"),
                    message="所选设备与客户明确指定或排除条件冲突，请核对选型或客户需求",
                    evidence=[dict(preference)],
                )
            )
    return checks


def budget_checks(data, checked):
    generation = data.get("generation", {})
    budget = generation.get("budget")
    if budget is None:
        return []
    total = (checked.get("quotation_output") or {}).get("total")
    status = (
        "unknown" if total is None else "conflict" if Decimal(total) > Decimal(budget) else "pass"
    )
    return [
        dict(
            kind="budget",
            code={
                "unknown": "budget_unknown",
                "conflict": "budget_exceeded",
                "pass": "budget_satisfied",
            }[status],
            status=status,
            budget=str(budget),
            total=total,
            message="金额未完整，不能判断预算是否满足"
            if total is None
            else f"报价 {total} 元，客户预算 {budget} 元",
            evidence=[dict(budget=str(budget), evidence=generation.get("budget_evidence", ""))],
        )
    ]
