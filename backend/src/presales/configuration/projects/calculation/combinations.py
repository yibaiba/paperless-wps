"""Resolve scope and explicit need links; ZEN decides combination legality."""

from decimal import Decimal

from presales.rules.calculation import digest

from ...decisions.combination import combination_result
from ...knowledge.combination_schemas import missing_combination
from ...knowledge.evaluator import context_for, scope_matches
from ...knowledge.semantics import condition_result, scope_is_reviewed
from ..planning.quantities import role_quantity
from .demands import applicable_roles, direct_owners, expand_owners
from .role_allocations import role_allocations


def combination_checks(data, *, variants, suggestions, definitions, engine, decisions):
    rules = [
        r
        for r in data["knowledge_snapshot"]
        if r["kind"] == "combination" and r["status"] != "disabled"
    ]
    if rules and decisions is None:
        raise ValueError("组合知识需要 ZEN 决策，请先预览运行时升级")
    systems = {s["id"]: s for s in data["systems"]}
    owners = direct_owners(data)
    while True:
        expanded = expand_owners(data, owners, suggestions)
        if expanded == owners:
            break
        owners = expanded
    checks = []
    for rule in rules:
        triggers = trigger_scopes(data, rule=rule, variants=variants, owners=owners)
        for scope_id, triggers_in_scope in triggers.items():
            groups = [
                target_state(
                    data,
                    target=t,
                    scope=rule["combination"].get("scope"),
                    scope_id=scope_id,
                    suggestions=suggestions,
                    definitions=definitions,
                    engine=engine,
                )
                for t in rule["combination"].get("targets", [])
            ]
            contexts = [
                context_for(variants[d], r.get("environment", [])) for d, r in triggers_in_scope
            ]
            activation = [
                condition_result(
                    [*rule.get("activation_conditions", []), *rule["conditions"]],
                    c,
                    decisions=decisions,
                )
                for c in contexts
            ]
            if all(a == "fail" for a in activation):
                continue
            missing = missing_combination(rule)
            unreviewed = any(not scope_is_reviewed(rule, variants[d]) for d, _ in triggers_in_scope)
            status = combination_result(decisions, mode=rule["combination"]["mode"], groups=groups)
            if rule["status"] != "confirmed" or "pass" not in activation or missing or unreviewed:
                status = "unknown"
            system_ids = [
                s["id"]
                for s in systems.values()
                if in_scope(s, rule["combination"].get("scope"), scope_id)
            ]
            checks.append(
                dict(
                    generation_enabled=rule["status"] == "confirmed"
                    and "pass" in activation
                    and not missing
                    and not unreviewed
                    and not scope_id.startswith("unknown:"),
                    kind="combination",
                    code="combination_" + rule["combination"]["mode"],
                    check_id=digest([rule["id"], rule["revision"], scope_id]),
                    status=status,
                    device_id=triggers_in_scope[0][0],
                    rule_id=rule["id"],
                    rule_revision=rule["revision"],
                    scope_id=scope_id,
                    scope=rule["combination"].get("scope"),
                    system_ids=system_ids,
                    device_ids=list(dict.fromkeys(d for d, _ in triggers_in_scope)),
                    groups=groups,
                    missing_fields=missing,
                    message=rule["name"]
                    + "："
                    + {
                        "pass": "组合条件满足",
                        "unknown": "组合依据或需求资料待确认",
                        "conflict": "组合要求未满足",
                    }[status]
                    + "（"
                    + "、".join(g["target"]["name"] for g in groups)
                    + "）",
                    evidence=[
                        dict(
                            id=rule["id"],
                            revision=rule["revision"],
                            name=rule["name"],
                            evidence=rule["evidence"],
                            evidence_refs=rule.get("evidence_refs", []),
                        )
                    ],
                )
            )
    return checks


def in_scope(system, scope, identity):
    return scope == "project" or bool(
        identity and system.get("id" if scope == "system" else "room_id") == identity
    )


def trigger_scopes(data, *, rule, variants, owners):
    systems = {s["id"]: s for s in data["systems"]}
    requirements = {r["id"]: r for r in data["requirements"]}
    groups = {}
    scope = rule["combination"].get("scope")
    for device in data["devices"]:
        if not scope_matches(variants[device["id"]], rule["selector"]):
            continue
        served = applicable_roles(
            [requirements[r] for r in sorted(owners[device["id"]])], rule, systems
        )
        for requirement in served:
            system = systems.get(requirement.get("system_id"), {})
            identity = (
                "project"
                if scope == "project"
                else system.get("id" if scope == "system" else "room_id")
            )
            groups.setdefault(identity or "unknown:" + device["id"], []).append(
                (device["id"], requirement)
            )
    return groups


def target_state(data, *, target, scope, scope_id, suggestions, definitions, engine):
    systems = {
        s["id"]: s
        for s in data["systems"]
        if in_scope(s, scope, scope_id)
        and (
            not target["system_definition_id"]
            or s.get("definition_id") == target["system_definition_id"]
        )
    }
    requirements = [
        r
        for r in data["requirements"]
        if r["system_id"] in systems
        and (not target["role_id"] or r.get("role_id") == target["role_id"])
    ]
    base = dict(
        target=target,
        system_ids=list(systems),
        requirement_ids=[r["id"] for r in requirements],
        demand_ids=[],
        state="unknown",
        present=False,
    )
    if target["need_key"]:
        return target_demands(data, base, suggestions=suggestions)
    if not target["role_id"]:
        return base
    states, allocations, alias_present = [], [], False
    devices = {d["id"]: d for d in data["devices"]}
    for requirement in requirements:
        assigned = [
            a
            for a in role_allocations(requirement, devices)
            if not target["variant_ids"]
            or devices[a["device_id"]]["variant_id"] in target["variant_ids"]
        ]
        allocations.extend(assigned)
        system = systems[requirement["system_id"]]
        role = role_definition(system, target["role_id"], definitions)
        fulfillment = role.get("fulfilled_by")
        if fulfillment:
            parents = [
                r["id"]
                for r in data["requirements"]
                if r["system_id"] == system["id"] and r.get("role_id") == fulfillment["role_id"]
            ]
            alias = target_demands(
                data,
                dict(
                    base,
                    target=dict(target, need_key=fulfillment["need_key"]),
                    requirement_ids=parents,
                ),
                suggestions=suggestions,
            )
            states.append(alias["state"] if fulfillment["status"] == "confirmed" else "unknown")
            base["demand_ids"].extend(alias["demand_ids"])
            alias_present = alias_present or alias["present"]
            continue
        needed, gap, _ = role_quantity(role, system, configuration=data, engine=engine)
        quantity = sum((Decimal(a["quantity"]) for a in assigned), Decimal(0))
        states.append("unknown" if gap else "pass" if needed > 0 and quantity >= needed else "fail")
    return dict(
        base,
        state=all_states(states),
        present=bool(allocations) or alias_present,
        allocations=allocations,
    )


def all_states(states):
    return (
        "fail" if "fail" in states else "unknown" if not states or "unknown" in states else "pass"
    )


def role_definition(system, role_id, definitions):
    package = next(
        (p for p in definitions["packages"] if p["id"] == system.get("knowledge_package_id")), None
    )
    definition = (
        package["definition"]
        if package
        else next(
            (d for d in definitions["definitions"] if d["id"] == system.get("definition_id")), {}
        )
    )
    return next((r for r in definition.get("roles", []) if r["id"] == role_id), dict(id=role_id))


def target_demands(data, base, *, suggestions):
    target = base["target"]
    demands = [
        s
        for s in suggestions
        if s["need_key"] == target["need_key"]
        and set(s["consumer_requirement_ids"]) & set(base["requirement_ids"])
    ]
    devices = {d["id"]: d for d in data["devices"]}
    states, present = [], False
    for demand in demands:
        allocated = [
            a
            for a in data["accessory_allocations"]
            if a["demand_id"] == demand["id"]
            and (
                not target["variant_ids"]
                or devices[a["device_id"]]["variant_id"] in target["variant_ids"]
            )
        ]
        from .inclusions import fact_for

        included = [
            a
            for a in data.get("included_allocations", [])
            if a["demand_id"] == demand["id"]
            and any(
                c["allocation_id"] == a["id"] and c["status"] == "pass"
                for c in demand.get("included_allocation_checks", [])
            )
            and (
                not target["variant_ids"]
                or (fact_for(devices[a["device_id"]], a["included_item_id"]) or {}).get(
                    "variant_id"
                )
                in target["variant_ids"]
            )
        ]
        present = present or bool(allocated or included)
        quantity = sum((Decimal(a["quantity"]) for a in [*allocated, *included]), Decimal(0))
        known = demand["status"] == "pass" and demand.get("required") is not None
        states.append(
            "unknown"
            if not known
            else "pass"
            if demand["selected"]
            and Decimal(demand["required"]) > 0
            and quantity >= Decimal(demand["required"])
            else "fail"
        )
    return dict(
        base, state=all_states(states), present=present, demand_ids=[d["id"] for d in demands]
    )
