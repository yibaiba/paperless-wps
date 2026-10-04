"""Addressable project inputs, separate from missing or unconfirmed knowledge."""

from ...catalog.attributes import attribute_definitions


def quantity_issues(entries, *, rule):
    if rule.get("quantity_source") != "environment" or not rule.get("quantity_key"):
        return []
    labels = {a["key"]: a["label"] for a in attribute_definitions()}
    issues = {}
    for entry in entries:
        origin = entry["input_origin"]
        if not origin.get("input_error_code") or not origin.get("input_scope_id"):
            continue
        targets = [(origin["input_scope"], origin["input_scope_id"])]
        requirement = entry["requirement"]
        if origin["input_conflict"]:
            targets.append(("role", requirement.get("allocation_parent_id", requirement.get("id"))))
        for scope, identity in targets:
            key = (scope, identity, rule["quantity_key"], rule.get("quantity_unit", ""))
            item = issues.setdefault(
                key,
                dict(
                    code=origin["input_error_code"],
                    scope=scope,
                    scope_id=identity,
                    key=rule["quantity_key"],
                    label=labels.get(rule["quantity_key"], rule["quantity_key"]),
                    unit=rule.get("quantity_unit", ""),
                    kind="quantity" if rule.get("quantity_unit") else "number",
                    message=entry["quantity"][1],
                    requirement_ids=[],
                    device_ids=[],
                ),
            )
            add_consumer(item, entry=entry)
    return list(issues.values())


def add_consumer(item, *, entry):
    requirement = entry["requirement"]
    for field, value in (
        ("requirement_ids", requirement.get("allocation_parent_id", requirement.get("id"))),
        ("device_ids", entry["device"]["id"]),
    ):
        if value and value not in item[field]:
            item[field].append(value)


def with_input_issues(demand, *, entries, knowledge_missing, cyclic):
    issues = quantity_issues(entries, rule=demand["rule"])
    return dict(
        demand,
        input_issues=issues,
        input_issues_only=bool(issues)
        and not knowledge_missing
        and not cyclic
        and all(e["rule_status"] == "pass" for e in entries),
    )
