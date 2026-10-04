from decimal import Decimal

from presales.rules.calculation import digest


def question(
    code, object_id, field, message, *, recipient="maintainer", evidence=None, choices=None
):
    return dict(
        id=digest(["proposal-question", code, object_id, field]),
        code=code,
        recipient=recipient,
        objects=[dict(id=object_id)],
        missing_fields=[field],
        message=message,
        choices=choices or [],
        evidence=evidence or [],
        action=dict(
            type="edit_requirements" if recipient == "customer" else "edit_knowledge",
            object_id=object_id,
            missing_fields=[field],
        ),
    )


def check_questions(checked):
    results = []
    checks = [*checked["checks"], *(checked.get("quotation_output") or {}).get("issues", [])]
    for check in checks:
        if check.get("status") == "pass":
            continue
        action = check.get("action") or {}
        identity = (
            check.get("check_id")
            or check.get("device_id")
            or check.get("requirement_id")
            or "project"
        )
        kind = check.get("code") or check.get("kind", "quotation")
        recipient = (
            "customer"
            if kind in {"product_constraint_conflict", "budget_exceeded"}
            or action.get("type")
            in {
                "edit_requirement",
                "edit_resources",
                "edit_system_inputs",
                "edit_supply",
                "add_system",
            }
            else "maintainer"
        )
        item = question(
            kind,
            identity,
            ",".join(action.get("missing_fields", [])) or kind,
            check.get("message") or "检查依据尚待核对",
            recipient=recipient,
            evidence=check.get("evidence", []),
            choices=check.get("choices", []),
        )
        item.update(status=check.get("status", "unknown"), check=check)
        results.append(item)
    for demand in checked["suggestions"]:
        if not demand["selected"] or (
            demand["status"] == "pass"
            and demand.get("missing") is not None
            and Decimal(demand["missing"]) == 0
        ):
            continue
        if demand.get("input_issues"):
            results.append(quantity_input_question(demand))
        if demand.get("input_issues_only"):
            continue
        results.append(
            question(
                "accessory_incomplete",
                demand["id"],
                "accessory",
                "；".join(demand.get("missing_information", [])) or "所需配套尚未满足",
                evidence=[demand.get("explanation", {})],
            )
        )
    return results


def quantity_input_question(demand):
    issues = demand["input_issues"]
    fields = list(dict.fromkeys(i["key"] for i in issues))
    item = question(
        "accessory_quantity_input",
        demand["id"],
        ",".join(fields),
        "；".join(dict.fromkeys(i["label"] + "：" + i["message"] for i in issues)),
        recipient="customer",
        evidence=[demand.get("explanation", {})],
    )
    return dict(
        item,
        status=demand["status"],
        missing_fields=fields,
        objects=[dict(kind=i["scope"], id=i["scope_id"]) for i in issues],
        action=dict(
            type="edit_quantity_inputs",
            demand_id=demand["id"],
            rule_id=demand["rule"]["id"],
            missing_fields=fields,
            quantity_inputs=issues,
        ),
    )


def unique_questions(items):
    return list({q["id"]: q for q in items}.values())
