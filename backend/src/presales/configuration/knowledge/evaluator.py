from decimal import Decimal, InvalidOperation


def scope_matches(variant, selector):
    if variant["id"] in selector["exclude_variant_ids"]:
        return False
    checks = []
    if selector["variant_ids"]:
        checks.append(variant["id"] in selector["variant_ids"])
    if selector["category"]:
        checks.append(variant["product"]["category"] == selector["category"])
    if selector["series"]:
        checks.append(bool(set(variant["series"]) & set(selector["series"])))
    return all(checks)


def context_for(variant, environment):
    attributes = {a["key"]: a for a in variant["attributes"]}
    result = {"product." + k: v for k, v in attributes.items()}
    result.update({"project." + a["key"]: a for a in environment})
    for key in ("series", "functions", "interfaces", "systems"):
        result["product." + key] = dict(value=variant[key] or None, unit="", kind="enum")
    return result


def check_condition(condition, context):
    actual = context.get(condition["field"])
    if actual is None or actual["value"] is None:
        return "unknown"
    if condition["unit"] != actual.get("unit", ""):
        return "unknown"
    value, expected = actual["value"], condition["value"]
    operator = condition["operator"]
    if operator == "eq":
        if actual.get("kind") in {"number", "quantity"}:
            try:
                return "pass" if Decimal(str(value)) == Decimal(str(expected)) else "fail"
            except InvalidOperation:
                return "unknown"
        return "pass" if str(value) == str(expected) else "fail"
    if operator in {"any", "all"}:
        values = set(value if isinstance(value, list) else [str(value)])
        matched = bool(values & set(expected)) if operator == "any" else set(expected) <= values
        return "pass" if matched else "fail"
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return "unknown"
    if not number.is_finite():
        return "unknown"
    below = condition["minimum"] is not None and number < Decimal(condition["minimum"])
    above = condition["maximum"] is not None and number > Decimal(condition["maximum"])
    return "fail" if below or above else "pass"


def evaluate_rules(rules, context):
    details = []
    for rule in rules:
        checks = [
            {**c, "actual": context.get(c["field"]), "result": check_condition(c, context)}
            for c in rule["conditions"]
        ]
        outcomes = {c["result"] for c in checks}
        result = "fail" if "fail" in outcomes else "unknown" if "unknown" in outcomes else "pass"
        details.append(
            dict(
                id=rule["id"],
                revision=rule["revision"],
                name=rule["name"],
                effect=rule["effect"],
                evidence=rule["evidence"],
                conditions=checks,
                result=result,
            )
        )
    allows = [d for d in details if d["effect"] == "allow"]
    denials = [d for d in details if d["effect"] == "deny"]
    denied = any(d["result"] == "pass" for d in denials)
    failed = any(d["result"] == "fail" for d in allows)
    unknown = not allows or any(d["result"] == "unknown" for d in details)
    status = "conflict" if denied or failed else "unknown" if unknown else "pass"
    return dict(status=status, evidence=details)


def candidate_check(variant, *, requirement, knowledge):
    applicable = [
        k
        for k in knowledge
        if k["status"] == "confirmed"
        and k["kind"] == "suitability"
        and k["system"] == requirement["system"]
        and k["role"] == requirement["role"]
        and scope_matches(variant, k["selector"])
    ]
    result = evaluate_rules(applicable, context_for(variant, requirement["environment"]))
    environment = environment_checks(variant, requirement["environment"], rules=applicable)
    if any(c["result"] == "fail" for c in environment):
        result["status"] = "conflict"
    elif result["status"] == "pass" and any(c["result"] == "unknown" for c in environment):
        result["status"] = "unknown"
    if environment:
        result["evidence"].append(
            dict(
                id=variant["id"],
                revision=variant["revision"],
                name="需求与产品参数对照",
                effect="allow",
                evidence=variant["evidence"],
                conditions=environment,
                result=result["status"],
            )
        )
    if variant["status"] != "confirmed" and result["status"] == "pass":
        result["status"] = "unknown"
    return dict(variant=variant, **result)


def environment_checks(variant, environment, *, rules):
    context = context_for(variant, [])
    accounted = {c["field"] for r in rules for c in r["conditions"]}
    checks = []
    for required in environment:
        # Project inputs remain in project.* for rules and quantities; they are
        # not assertions that the selected product has an identical attribute.
        if required.get("purpose") == "project_input":
            continue
        field = "product." + required["key"]
        if field not in context and "project." + required["key"] in accounted:
            continue
        actual = context.get(field)
        expected = required["value"]
        multi = isinstance(expected, list) or (actual and isinstance(actual["value"], list))
        condition = dict(
            field=field,
            operator="any" if multi else "eq",
            value=expected if isinstance(expected, list) or not multi else [expected],
            unit=required["unit"],
            minimum=None,
            maximum=None,
        )
        status = check_condition(condition, context) if expected is not None else "unknown"
        checks.append(dict(**condition, actual=actual, result=status))
    return checks
