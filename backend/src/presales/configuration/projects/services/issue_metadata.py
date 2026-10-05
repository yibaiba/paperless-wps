"""Stable issue references and conservative grouping, without parsing display messages."""

from presales.rules.calculation import digest

CATEGORIES = {
    "select_candidate": "selection",
    "edit_accessory": "selection",
    "assign_device": "selection",
    "edit_supply": "commercial",
    "edit_price": "commercial",
    "add_system": "requirements",
    "add_requirement": "requirements",
    "edit_requirement": "requirements",
    "edit_resources": "requirements",
    "edit_system_inputs": "requirements",
}


def annotate_issues(checks):
    result = []
    occurrences = {}
    for check in checks:
        action = check.get("action", {})
        code = check.get("code") or check["kind"]
        objects = [
            {"kind": key.removesuffix("_id"), "id": check[key]}
            for key in ("system_id", "requirement_id", "device_id", "demand_id", "allocation_id")
            if check.get(key)
        ]
        for identity in action.get("requirement_ids", []):
            item = dict(kind="requirement", id=identity)
            if item not in objects:
                objects.append(item)
        for kind, field in (
            ("allocation_group", "allocation_group_ids"),
            ("device", "device_ids"),
            ("demand", "demand_ids"),
        ):
            for identity in action.get(field, []):
                item = dict(kind=kind, id=identity)
                if item not in objects:
                    objects.append(item)
        if action.get("allocation_group_id"):
            objects.append(dict(kind="allocation_group", id=action["allocation_group_id"]))
        if check["kind"] == "interpretation":
            objects.extend(
                [
                    dict(kind="requirement_source", id=check["source_id"]),
                    dict(kind="requirement_object", id=check["object_id"]),
                ]
            )
        cause = dict(
            code=code,
            resource=check.get("resource"),
            profile_id=check.get("profile_id"),
            rule_id=check.get("rule_id"),
            fields=action.get("missing_fields", []),
        )
        identity = digest(dict(cause=cause, objects=objects))
        occurrence = occurrences.get(identity, 0)
        occurrences[identity] = occurrence + 1
        identity = f"{identity}:{occurrence}"
        # Only a known shared rule with identical evidence can group separate objects.
        group = (
            digest(dict(cause=cause, evidence=check.get("evidence"), status=check["status"]))
            if cause["rule_id"]
            else identity
        )
        result.append(
            dict(
                check,
                code=code,
                check_id=identity,
                group_id=group,
                category=CATEGORIES.get(action.get("type"), "knowledge"),
                objects=objects,
            )
        )
    return result
