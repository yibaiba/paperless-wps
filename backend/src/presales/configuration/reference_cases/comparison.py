"""Explicit case bindings explain differences; the case never determines purchasing."""

from decimal import Decimal

from ..common import Entities
from .quantities import mapped_quantity
from .service import case_revision, system_features
from .status import conclusion


def compare_case(session, checked):
    configuration = checked["configuration"]
    reference = configuration.get("reference_case")
    if not reference:
        return dict(
            case=None,
            rows=[],
            additional=[],
            notice="尚未关联参考案例",
            available_cases=[
                dict(id=c["id"], revision=c["revision"], name=c["name"], row_count=len(c["rows"]))
                for c in Entities(session).list("reference_case")
            ],
        )
    case = case_revision(session, reference["id"], reference["revision"])
    bindings = {b["row_id"]: b for b in reference["bindings"]}
    context = dict(
        known_features=system_features(session, configuration)
        if any(b["disposition"] == "not_enabled" for b in bindings.values())
        else {},
        configuration=configuration,
        checked=checked,
        devices={d["id"]: d for d in configuration["devices"]},
        lines={line["device_id"]: line for line in checked["project_output"]["lines"]},
    )
    rows = [compare_row(row, bindings.get(row["id"]), context=context) for row in case["rows"]]
    used = {d for row in rows for d in row["device_ids"]}
    return dict(
        case={k: v for k, v in case.items() if k != "rows"},
        rows=rows,
        additional=[line for identity, line in context["lines"].items() if identity not in used],
        notice="参考案例用于逐项对照，不是采购规则；跨行共用的设备仅在实际采购清单计量一次。",
    )


def resolved_ids(binding, context):
    configuration = context["configuration"]
    ids = set(binding["device_ids"])
    for role in configuration["requirements"]:
        if role["id"] not in binding["requirement_ids"]:
            continue
        ids.update(a["device_id"] for a in role.get("allocations", []))
        if role.get("device_id"):
            ids.add(role["device_id"])
    ids.update(
        a["device_id"]
        for a in configuration["accessory_allocations"]
        if a["demand_id"] in binding["demand_ids"]
    )
    return sorted(ids)


def compare_row(row, binding, *, context):
    result = dict(
        row_id=row["id"],
        original=row,
        binding=binding,
        status="unknown",
        reason="尚未明确关联需求、配套或设备",
        device_ids=[],
        current=[],
        deployed="0",
        purchase="0",
        existing="0",
        included="0",
        quantity_delta=None,
        mapped_quantity=None,
        issues=[],
        actions=[],
    )
    if binding is None:
        return result
    identities = resolved_ids(binding, context)
    missing = [i for i in identities if i not in context["devices"]]
    lines = [context["lines"][i] for i in identities if i in context["lines"]]
    checks = relevant_checks(binding, identities, context)
    units_differ = any(line.get("unit", row.get("unit")) != row.get("unit") for line in lines)
    if units_differ:
        checks.append(dict(status="unknown", message="原清单与当前配置单位不同，数量不可直接相减"))
    mapped, mapping_issues = mapped_quantity(binding, context, identities)
    totals = line_totals(lines)
    included, inclusion_issues = included_quantity(binding, context)
    result.update(
        device_ids=identities,
        current=lines,
        **totals,
        included=str(included),
        mapped_quantity=str(mapped + included) if mapped is not None else None,
        issues=checks + inclusion_issues + mapping_issues,
        actions=[c["action"] for c in checks if c.get("action")],
    )
    if row["quantity"] is not None and not units_differ and mapped is not None:
        result["quantity_delta"] = str(mapped + included - Decimal(row["quantity"]))
    status, reason = conclusion(row, binding, context=context, result=result, missing=missing)
    return dict(result, status=status, reason=reason, evidence=binding["evidence"])


def line_totals(lines):
    return dict(
        deployed=str(sum((Decimal(line["quantity"]) for line in lines), Decimal(0))),
        purchase=str(
            sum(
                (Decimal(line.get("supply", {}).get("purchase", "0")) for line in lines), Decimal(0)
            )
        ),
        existing=str(
            sum(
                (Decimal(line.get("supply", {}).get("existing", "0")) for line in lines), Decimal(0)
            )
        ),
    )


def relevant_checks(binding, identities, context):
    objects = (
        set(identities)
        | set(binding["requirement_ids"])
        | set(binding["demand_ids"])
        | set(binding["included_allocation_ids"])
    )
    return [
        c
        for c in context["checked"].get("checks", [])
        if c["status"] != "pass"
        and (
            objects & {o["id"] for o in c.get("objects", [])}
            or objects
            & {
                c.get("device_id"),
                c.get("requirement_id"),
                c.get("demand_id"),
                c.get("allocation_id"),
            }
        )
    ]


def included_quantity(binding, context):
    allocations = {a["id"]: a for a in context["configuration"].get("included_allocations", [])}
    total, issues = Decimal(0), []
    for identity in binding["included_allocation_ids"]:
        item = allocations.get(identity)
        if item is None:
            issues.append(
                dict(status="unknown", message="已含抵扣已被移除", allocation_id=identity)
            )
            continue
        check = next(
            (
                c
                for c in context["checked"].get("checks", [])
                if c.get("kind") == "included_allocation" and c.get("allocation_id") == identity
            ),
            None,
        )
        if check is None or check["status"] != "pass":
            issues.append(
                dict(status="unknown", message="已含抵扣尚未通过配套检查", allocation_id=identity)
            )
            continue
        total += Decimal(check["counted_quantity"])
    return total, issues
