from collections import defaultdict
from decimal import Decimal

from ...knowledge.evaluator import context_for, scope_matches
from ...knowledge.package_scope import package_allows
from ...knowledge.semantics import condition_result, evaluate_rules_v3, scope_is_reviewed
from ..accessory_demands import (
    calculated_demand,
    cyclic_rule_ids,
    demand_base,
    denial_rules,
    rule_missing,
)
from .demand_identity import DemandIdentities
from .quantity_inputs import quantity_input


def accessory_demands_v3(data, *, variants, catalog_variants, engine, decisions=None):
    rules = [
        r
        for r in data["knowledge_snapshot"]
        if r["kind"] == "accessory" and r["status"] != "disabled"
    ]
    owners = direct_owners(data)
    identities = DemandIdentities(data, rules=rules)
    # Only fixed project configurations participate; later catalogue edits cannot alter history.
    cycles = scoped_cycles(data, rules, variants.values())
    while True:
        demands = collect_demands(
            data,
            rules=rules,
            owners=owners,
            variants=variants,
            engine=engine,
            cycles=cycles,
            identities=identities,
            decisions=decisions,
        )
        expanded = expand_owners(data, owners, demands)
        if expanded == owners:
            return demands
        owners = expanded


def direct_owners(data):
    result = {d["id"]: set() for d in data["devices"]}
    for requirement in data["requirements"]:
        if requirement.get("device_id") in result:
            result[requirement["device_id"]].add(requirement["id"])
    return result


def expand_owners(data, owners, demands):
    expanded = {identity: set(values) for identity, values in owners.items()}
    by_id = {d["id"]: d for d in demands}
    for allocation in data["accessory_allocations"]:
        demand = by_id.get(allocation["demand_id"])
        if demand and demand["selected"] and allocation["device_id"] in expanded:
            expanded[allocation["device_id"]].update(demand["consumer_requirement_ids"])
    return expanded


def collect_demands(data, *, rules, owners, variants, engine, cycles, identities, decisions=None):
    results = []
    for rule in rules:
        if rule["effect"] != "allow":
            continue
        groups = contributions(
            data, rule=rule, owners=owners, variants=variants, decisions=decisions
        )
        for scope_id, entries in groups.items():
            identity = identities.identity(rule, scope_id)
            missing = quantity_missing(rule)
            if missing:
                demand = incomplete_demand(rule, scope_id, entries, missing, identity=identity)
            else:
                demand = calculated_demand(
                    data,
                    rule,
                    scope_id,
                    entries,
                    engine,
                    demand_has_cycle(data, rule, entries, cycles=cycles),
                    demand_id=identity,
                )
            demand["quantity_inputs"] = [input_evidence(rule, entry) for entry in entries]
            results.append(with_selection(data, demand))
    return results


def quantity_missing(rule):
    labels = {
        "mode": "计算方式待确认",
        "factor": "计算系数待确认",
        "target_variant_ids": "配套候选待确认",
        "calculation_scope": "计算范围待确认",
        "quantity_key": "数量输入参数待确认",
    }
    missing = [labels.get(field, field) for field in rule_missing(rule)]
    if rule["status"] != "confirmed":
        missing.append("关系尚未确认")
    if rule.get("quantity_review") != "confirmed":
        missing.append("数量依据尚未确认（历史公式也需核对）")
    return missing


def incomplete_demand(rule, scope_id, entries, missing, *, identity):
    consumers = list(
        dict.fromkeys(e["requirement"]["id"] for e in entries if e["requirement"].get("id"))
    )
    return dict(
        demand_base(rule, identity, scope_id, consumers),
        status="unknown",
        required=None,
        existing="0",
        missing=None,
        surplus="0",
        missing_information=missing,
        evidence=[ev for entry in entries for ev in entry["evaluation"]["evidence"]],
        calculation=None,
    )


def with_selection(data, demand):
    choices = {c["demand_id"]: c for c in data.get("accessory_choices", [])}
    required = demand["rule"].get("accessory_type", "required") == "required"
    allocated = any(
        a["demand_id"] == demand["id"]
        for a in [*data["accessory_allocations"], *data.get("included_allocations", [])]
    )
    choice = choices.get(demand["id"])
    selected = required or (choice["selected"] if choice else allocated)
    return dict(
        demand,
        selected=selected,
        selection_conflict=bool(allocated and choice and not choice["selected"]),
        explanation=dict(
            rule_id=demand["rule"]["id"],
            rule_revision=demand["rule"]["revision"],
            scope=demand["scope"],
            scope_id=demand["scope_id"],
            evidence_refs=demand["rule"].get("evidence_refs", []),
            quantity_inputs=demand.get("quantity_inputs", []),
        ),
    )


def contributions(data, *, rule, owners, variants, decisions=None):
    systems = {s["id"]: s for s in data["systems"]}
    requirements = {r["id"]: r for r in data["requirements"]}
    grouped, counted = defaultdict(list), set()
    for device in data["devices"]:
        variant = variants[device["id"]]
        if not scope_matches(variant, rule["selector"]):
            continue
        served = [requirements[key] for key in sorted(owners[device["id"]])]
        served = applicable_roles(served, rule, systems)
        for requirement in served:
            context = context_for(variant, requirement.get("environment", []))
            activation = condition_result(
                rule.get("activation_conditions", []), context, decisions=decisions
            )
            if activation == "fail":
                continue
            scope_id = scope_identity(rule, device, requirement, systems)
            package_id = systems.get(requirement.get("system_id"), {}).get("knowledge_package_id")
            denials = [
                r for r in denial_rules(data, rule, variant) if package_allows(r, package_id)
            ]
            evaluation = evaluate_rules_v3([rule, *denials], context, decisions=decisions)
            if not scope_id:
                scope_id = "unknown:" + device["id"]
                evaluation = dict(evaluation, status="unknown")
            if not scope_is_reviewed(rule, variant):
                evaluation = dict(evaluation, status="unknown")
            entry, key = prepare_contribution(
                data,
                rule=rule,
                device=device,
                requirement=requirement,
                system=systems.get(requirement.get("system_id"), {}),
                scope_id=scope_id,
                evaluation=evaluation,
                counted=counted,
            )
            counted.add(key)
            grouped[scope_id].append(entry)
    return grouped


def prepare_contribution(data, *, rule, device, requirement, system, scope_id, evaluation, counted):
    allocated = (
        requirement.get("allocated_quantity")
        if requirement.get("device_id") == device["id"]
        else None
    )
    contributing = dict(device, quantity=allocated) if allocated is not None else device
    quantity, origin = quantity_input(
        data, rule=rule, device=contributing, requirement=requirement, system=system
    )
    origin = dict(origin, input_value=str(quantity[0]) if quantity[0] is not None else None)
    if origin["input_conflict"]:
        evaluation = dict(evaluation, status="conflict")
    key = contribution_key(
        rule, scope_id=scope_id, device=device, requirement=requirement, origin=origin
    )
    reused = key in counted
    if reused and quantity[1] is None:
        quantity = (Decimal(0), None)
    if not rule.get("calculation_scope") or scope_id.startswith("unknown:"):
        quantity = (None, "设备缺少已确认的计算范围或归属")
    return dict(
        device=device,
        requirement=requirement,
        evaluation=evaluation,
        quantity=quantity,
        input_origin=dict(origin, reused=reused),
    ), key


def input_evidence(rule, entry):
    device, requirement = entry["device"], entry["requirement"]
    return dict(
        device_id=device["id"],
        variant_id=device["variant_id"],
        source_id=device["source_id"],
        variant_revision=(device.get("variant_snapshot") or {}).get("revision"),
        requirement_id=requirement.get("id"),
        value=str(entry["quantity"][0]) if entry["quantity"][0] is not None else None,
        parameter=rule.get("quantity_key")
        if rule.get("quantity_source") == "environment"
        else "device_quantity",
        unit=rule.get("quantity_unit", "")
        if rule.get("quantity_source") == "environment"
        else "台/项",
        error=entry["quantity"][1],
        **entry["input_origin"],
    )


def applicable_roles(served, rule, systems):
    if not served:
        return [{}] if package_allows(rule, None) else []
    result = []
    for requirement in served:
        system = systems[requirement["system_id"]]
        if not package_allows(rule, system.get("knowledge_package_id")):
            continue
        if rule.get("system_definition_id"):
            if rule["system_definition_id"] != system.get("definition_id"):
                continue
        elif rule.get("system") and rule["system"] != system["kind"]:
            continue
        if rule.get("role_id"):
            if rule["role_id"] != requirement.get("role_id"):
                continue
        elif rule.get("role") and rule["role"] != requirement["role"]:
            continue
        result.append(requirement)
    return result


def scope_identity(rule, device, requirement, systems):
    scope = rule.get("calculation_scope")
    if scope == "device":
        return device["id"]
    if scope == "project":
        return "project"
    system = systems.get(requirement.get("system_id"), {})
    return system.get("id" if scope == "system" else "room_id")


def contribution_key(rule, *, scope_id, device, requirement, origin):
    if rule.get("quantity_source") == "environment":
        return (scope_id, origin["input_scope"], origin["input_scope_id"], rule["quantity_key"])
    if (
        Decimal(device["quantity"]) > 1
        and requirement.get("device_id") == device["id"]
        and requirement.get("allocated_quantity") is not None
    ):
        return (scope_id, device["id"], requirement["id"])
    return (scope_id, device["id"])


def scoped_cycles(data, rules, variants):
    packages = {s.get("knowledge_package_id") for s in data["systems"]} | {None}
    return {
        package: cyclic_rule_ids([r for r in rules if package_allows(r, package)], variants)
        for package in packages
    }


def demand_has_cycle(data, rule, entries, *, cycles):
    systems = {s["id"]: s for s in data["systems"]}
    return any(
        rule["id"]
        in cycles[systems.get(e["requirement"].get("system_id"), {}).get("knowledge_package_id")]
        for e in entries
    )
