"""Describe potential accessory inputs without selecting or certifying a candidate."""

from ..knowledge.evaluator import scope_matches
from ..knowledge.semantics import role_matches


def accepts(selector, identity, variants):
    if identity in selector.get("exclude_variant_ids", []):
        return False
    variant = variants.get(identity)
    if variant:
        return scope_matches(variant, selector)
    # Explicit IDs are enough to describe inputs, never to certify suitability.
    return identity in selector.get("variant_ids", [])


def roots_for(requirement, rules, variants):
    related = [
        r
        for r in rules
        if r.get("kind") == "suitability"
        and r.get("effect", "allow") == "allow"
        and r["status"] != "disabled"
        and role_matches(r, requirement)
    ]
    identities = {v for r in related for v in r["selector"].get("variant_ids", [])}
    identities.update(
        v for v in variants if any(accepts(r["selector"], v, variants) for r in related)
    )
    return sorted(
        v for v in identities if any(accepts(r["selector"], v, variants) for r in related)
    )


def input_field(rule, *, root, role, attributes, conditional, path):
    key = rule.get("quantity_key")
    if rule.get("quantity_source") != "environment" or not key:
        return None
    unit = rule.get("quantity_unit", "")
    return dict(
        key=key,
        label=attributes.get(key, {}).get("label", key + "（未注册字段）"),
        kind="quantity" if unit else "number",
        unit=unit,
        scope="role"
        if rule.get("calculation_scope") == "device"
        else rule.get("calculation_scope") or "role",
        purpose="project_input",
        conditional=conditional,
        consumer_role_ids=[role["id"]],
        candidate_variant_ids=[root] if root else [],
        need_keys=[rule.get("need_key", "")],
        evidence=[
            dict(
                kind="accessory_quantity",
                id=rule["id"],
                revision=rule["revision"],
                status=rule["status"],
                quantity_review=rule.get("quantity_review", "unreviewed"),
                conditions=rule.get("conditions", []),
                activation_conditions=rule.get("activation_conditions", []),
                rule_path=path,
                evidence_refs=rule.get("evidence_refs", []),
            )
        ],
    )


def accessory_inputs(requirement, *, role, rules, variants, attributes):
    applicable = [
        r
        for r in rules
        if r.get("kind") == "accessory"
        and r["status"] != "disabled"
        and r.get("effect", "allow") == "allow"
        and role_matches(r, requirement, allow_unrestricted=True)
    ]
    roots = roots_for(requirement, rules, variants)
    fields, gaps = [], []
    for root in roots:
        found, issues = traverse(
            root, rules=applicable, role=role, variants=variants, attributes=attributes
        )
        fields.extend(found)
        gaps.extend(issues)
    # An explicitly role-bound rule can describe its input before suitability is maintained.
    for rule in applicable:
        if roots or not (rule.get("role_id") or rule.get("role")):
            continue
        field = input_field(
            rule, root="", role=role, attributes=attributes, conditional=True, path=[rule["id"]]
        )
        if field:
            fields.append(field)
    return fields, gaps


def traverse(root, *, rules, role, variants, attributes):
    pending = [(root, [root], [], False)]
    fields, gaps = [], []
    while pending:
        identity, ancestors, path, optional = pending.pop()
        for rule in rules:
            if not accepts(rule["selector"], identity, variants):
                continue
            conditional = (
                optional
                or rule.get("accessory_type") != "required"
                or bool(
                    rule.get("conditions")
                    or rule.get("activation_conditions")
                    or rule["status"] != "confirmed"
                )
            )
            rule_path = [*path, rule["id"]]
            field = input_field(
                rule,
                root=root,
                role=role,
                attributes=attributes,
                conditional=conditional,
                path=rule_path,
            )
            if field:
                fields.append(field)
            for target in rule.get("target_variant_ids", []):
                if target in ancestors:
                    gaps.append(
                        dict(
                            code="accessory_input_cycle",
                            role_id=role["id"],
                            candidate_variant_id=root,
                            rule_ids=rule_path,
                            variant_ids=[*ancestors, target],
                            message="配套输入存在循环依赖",
                        )
                    )
                else:
                    pending.append((target, [*ancestors, target], rule_path, conditional))
    return fields, gaps


def merged_inputs(fields, role_id):
    merged = {}
    for field in fields:
        identity = (field["scope"], field["key"], field["kind"], field["unit"], field["purpose"])
        if identity not in merged:
            merged[identity] = dict(field)
            continue
        old = merged[identity]
        for key in ("evidence", "candidate_variant_ids", "consumer_role_ids", "need_keys"):
            old[key] = unique([*old.get(key, []), *field.get(key, [])])
        old["conditional"] = old.get("conditional", False) and field.get("conditional", False)
    values = list(merged.values())
    gaps = []
    for field in values:
        peers = [f for f in values if (f["scope"], f["key"]) == (field["scope"], field["key"])]
        if len({(f["kind"], f["unit"], f["purpose"]) for f in peers}) > 1:
            gaps.append(
                dict(
                    code="input_definition_conflict",
                    role_id=role_id,
                    key=field["key"],
                    scope=field["scope"],
                    message="同一输入的类型、用途或单位存在差异",
                )
            )
    return values, unique(gaps)


def unique(items):
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
