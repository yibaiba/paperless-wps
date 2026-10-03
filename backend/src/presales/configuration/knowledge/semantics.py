"""Explicit activation and alternative groups for calculation version 3."""

from collections import defaultdict

from .evaluator import check_condition, context_for, environment_checks, scope_matches
from .package_scope import package_allows


def condition_result(conditions, context, *, decisions=None):
    if decisions is not None:
        return decisions.condition_result(conditions, context)
    outcomes = {check_condition(item, context) for item in conditions}
    return "fail" if "fail" in outcomes else "unknown" if "unknown" in outcomes else "pass"


def rule_evidence(rule, context):
    activation = condition_result(rule.get("activation_conditions", []), context)
    conditions = [
        {**item, "actual": context.get(item["field"]), "result": check_condition(item, context)}
        for item in rule["conditions"]
    ]
    result = condition_result(rule["conditions"], context)
    if activation != "pass":
        result = "not_applicable" if activation == "fail" else "unknown"
    return dict(
        id=rule["id"],
        revision=rule["revision"],
        name=rule["name"],
        effect=rule["effect"],
        evidence=rule["evidence"],
        conditions=conditions,
        activation=activation,
        activation_conditions=rule.get("activation_conditions", []),
        alternative_group=rule.get("alternative_group", ""),
        result=result,
        evidence_refs=rule.get("evidence_refs", []),
    )


def alternative_result(items):
    states = {item["result"] for item in items}
    if "pass" in states:
        return "pass"
    if "unknown" in states:
        return "unknown"
    return "fail" if "fail" in states else "not_applicable"


def evaluate_rules_v3(rules, context, *, decisions=None):
    if decisions is not None:
        return decisions.evaluate_rules(rules, context)
    details = [rule_evidence(rule, context) for rule in rules]
    denials = {item["result"] for item in details if item["effect"] == "deny"}
    groups = defaultdict(list)
    for item in details:
        if item["effect"] == "allow":
            groups[item["alternative_group"] or item["id"]].append(item)
    outcomes = {alternative_result(items) for items in groups.values()}
    if "pass" in denials or "fail" in outcomes:
        status = "conflict"
    elif "unknown" in denials or "unknown" in outcomes or "pass" not in outcomes:
        status = "unknown"
    else:
        status = "pass"
    return dict(status=status, evidence=details)


def role_matches(rule, requirement, *, allow_unrestricted=False):
    if not package_allows(rule, requirement.get("knowledge_package_id")):
        return False
    for identity, label in (("system_definition_id", "system"), ("role_id", "role")):
        if rule.get(identity):
            if rule[identity] != requirement.get(identity):
                return False
        elif not (allow_unrestricted and not rule.get(label)):
            if rule.get(label, "") != requirement.get(label, ""):
                return False
    return True


def shared_roles_match(rule, uses):
    if not all(package_allows(rule, use.get("knowledge_package_id")) for use in uses):
        return False
    if rule.get("shared_role_refs"):
        roles = {(u.get("system_definition_id"), u.get("role_id")) for u in uses}
        return roles <= {
            (r["system_definition_id"], r["role_id"]) for r in rule["shared_role_refs"]
        }
    return {u["system"] + "/" + u["role"] for u in uses} <= set(rule.get("shared_roles", []))


def candidate_check_v3(variant, *, requirement, knowledge, decisions=None):
    rules = [
        item
        for item in knowledge
        if item["kind"] == "suitability"
        and item["status"] == "confirmed"
        and role_matches(item, requirement)
        and scope_matches(variant, item["selector"])
    ]
    unreviewed = [r for r in rules if not scope_is_reviewed(r, variant)]
    context = context_for(variant, requirement["environment"])
    result = evaluate_rules_v3(rules, context, decisions=decisions)
    active = [
        item
        for item in rules
        if condition_result(item.get("activation_conditions", []), context, decisions=decisions)
        != "fail"
    ]
    accounted = [
        dict(item, conditions=[*item["conditions"], *item.get("activation_conditions", [])])
        for item in active
    ]
    environment = environment_checks(
        variant,
        requirement["environment"],
        rules=accounted,
        condition_checker=decisions.check_condition if decisions else None,
    )
    if any(item["result"] == "fail" for item in environment):
        result["status"] = "conflict"
    elif result["status"] == "pass" and (
        variant["status"] != "confirmed" or any(c["result"] == "unknown" for c in environment)
    ):
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
    if unreviewed and result["status"] == "pass":
        result["status"] = "unknown"
        result["evidence"].append(
            dict(
                name="共性知识范围待核对",
                evidence="当前配置不在已核对配置中，原依据未声明覆盖整个系列",
                result="unknown",
            )
        )
    missing = set(requirement.get("capability_ids", [])) - set(variant.get("capability_ids", []))
    if missing:
        if result["status"] == "pass":
            result["status"] = "unknown"
        result["evidence"].append(
            dict(
                name="角色能力待核对",
                result="unknown",
                evidence="当前配置未登记角色所需能力：" + "、".join(sorted(missing)),
            )
        )
    return dict(variant=variant, **result)


def role_capabilities(requirement, definitions):
    package = next(
        (p for p in definitions["packages"] if p["id"] == requirement.get("knowledge_package_id")),
        None,
    )
    definition = (
        package["definition"]
        if package
        else next(
            (
                d
                for d in definitions["definitions"]
                if d["id"] == requirement.get("system_definition_id")
            ),
            {},
        )
    )
    role = next(
        (r for r in definition.get("roles", []) if r["id"] == requirement.get("role_id")), {}
    )
    return role.get("capability_ids", [])


def scope_is_reviewed(rule, variant):
    if rule.get("schema_version", 1) == 1 or rule.get("scope_basis") == "entire_scope":
        return True
    explicit = set(rule["selector"]["variant_ids"]) | set(rule.get("reviewed_variant_ids", []))
    return variant["id"] in explicit
