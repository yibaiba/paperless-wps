from collections import defaultdict
from decimal import Decimal, InvalidOperation

from presales.rules.calculation import digest

from ..knowledge.evaluator import context_for, evaluate_rules, scope_matches
from .accessory_allocations import demand_quantities


def calculate_accessory_demands(data, *, variants, catalog_variants, engine):
    rules = [
        item
        for item in data["knowledge_snapshot"]
        if item["kind"] == "accessory" and item["status"] != "disabled"
    ]
    cycles = cyclic_rule_ids(rules, catalog_variants.values())
    demands = []
    for rule in (item for item in rules if item["effect"] == "allow"):
        sources = [
            device
            for device in data["devices"]
            if scope_matches(variants[device["id"]], rule["selector"])
        ]
        if rule["status"] != "confirmed" or rule_missing(rule):
            demands.extend(pending_demands(data, rule, sources))
            continue
        grouped, pending = group_contributions(data, rule, sources, variants)
        demands.extend(pending)
        for scope_id, contributions in grouped.items():
            demands.append(
                calculated_demand(
                    data,
                    rule,
                    scope_id,
                    contributions,
                    engine,
                    rule["id"] in cycles,
                )
            )
    return demands


def rule_missing(rule):
    required = ("target_variant_ids", "calculation_scope", "mode", "factor")
    missing = [key for key in required if not rule.get(key) and rule.get(key) != 0]
    if rule.get("quantity_source") == "environment" and not rule.get("quantity_key"):
        missing.append("quantity_key")
    return missing


def pending_demands(data, rule, devices):
    missing = ["知识尚未确认"] if rule["status"] != "confirmed" else []
    missing.extend(rule.get("missing_fields") or rule_missing(rule))
    return [
        demand_base(
            rule,
            digest([rule["id"], "pending", device["id"]]),
            device["id"],
            consumer_requirement_ids(data, device["id"]),
        )
        | {
            "status": "unknown",
            "required": None,
            "existing": "0",
            "missing": None,
            "surplus": "0",
            "missing_information": list(dict.fromkeys(missing)),
            "evidence": [],
            "calculation": None,
        }
        for device in devices
    ]


def group_contributions(data, rule, devices, variants):
    systems = {item["id"]: item for item in data["systems"]}
    requirements = data["requirements"]
    grouped = defaultdict(list)
    pending = []
    for device in devices:
        served = [item for item in requirements if item["device_id"] == device["id"]]
        entries = contribution_entries(rule, device, served, systems)
        if not entries:
            pending.append(unknown_scope(rule, device))
            continue
        denials = denial_rules(data, rule, variants[device["id"]])
        for scope_id, requirement in entries:
            context = context_for(variants[device["id"]], requirement.get("environment", []))
            evaluation = evaluate_rules([rule, *denials], context)
            quantity = contribution_quantity(rule, device, requirement)
            grouped[scope_id].append(
                dict(
                    device=device,
                    requirement=requirement,
                    evaluation=evaluation,
                    quantity=quantity,
                )
            )
    return grouped, pending


def contribution_entries(rule, device, requirements, systems):
    scope = rule["calculation_scope"]
    if scope == "device":
        return [(device["id"], requirements[0] if requirements else {})]
    if scope == "project":
        return [("project", requirements[0] if requirements else {})]
    result = []
    for requirement in requirements:
        system = systems[requirement["system_id"]]
        scope_id = system["id"] if scope == "system" else system.get("room_id")
        if scope_id:
            result.append((scope_id, requirement))
    return unique_entries(result, rule)


def unique_entries(entries, rule):
    if rule.get("quantity_source") == "environment":
        return entries
    unique = {}
    for scope_id, requirement in entries:
        unique.setdefault(scope_id, requirement)
    return list(unique.items())


def contribution_quantity(rule, device, requirement):
    if rule.get("quantity_source", "device_quantity") == "device_quantity":
        return Decimal(device["quantity"]), None
    attribute = next(
        (
            item
            for item in requirement.get("environment", [])
            if item["key"] == rule["quantity_key"]
        ),
        None,
    )
    if not attribute or attribute["value"] is None:
        return None, "缺少需求参数：" + rule["quantity_key"]
    try:
        value = Decimal(str(attribute["value"]))
    except (InvalidOperation, TypeError):
        return None, "需求参数不是有效数值：" + rule["quantity_key"]
    return value, None


def calculated_demand(data, rule, scope_id, contributions, engine, cyclic, *, demand_id=None):
    demand_id = demand_id or digest([rule["id"], rule["calculation_scope"], scope_id])
    evidence = [
        item
        for contribution in contributions
        for item in contribution["evaluation"]["evidence"]
    ]
    errors = [item["quantity"][1] for item in contributions if item["quantity"][1]]
    statuses = {item["evaluation"]["status"] for item in contributions}
    if cyclic:
        errors.append("配套关系形成循环，请先调整知识")
    if cyclic or "conflict" in statuses:
        status = "conflict"
    elif errors or "unknown" in statuses:
        status = "unknown"
    else:
        status = "pass"
    if status != "pass":
        return incomplete_calculation(
            rule,
            demand_id,
            scope_id,
            status,
            errors,
            evidence,
            contribution_requirement_ids(contributions),
        )
    quantity = sum((item["quantity"][0] for item in contributions), Decimal(0))
    calculated = engine.calculate(mode=rule["mode"], quantity=str(quantity), factor=rule["factor"])
    required = Decimal(calculated["quantity"])
    existing, allocation_errors = allocated_quantity(data, demand_id, rule)
    if allocation_errors:
        status = "conflict"
    return demand_base(
        rule, demand_id, scope_id, contribution_requirement_ids(contributions)
    ) | {
        "status": status,
        "required": str(required),
        "existing": str(existing),
        "missing": str(max(required - existing, Decimal(0))),
        "surplus": str(max(existing - required, Decimal(0))),
        "missing_information": allocation_errors,
        "evidence": evidence,
        "calculation": {k: calculated[k] for k in ("engine", "expression", "input")},
    }


def allocated_quantity(data, demand_id, rule):
    devices = {item["id"]: item for item in data["devices"]}
    quantities = demand_quantities(data.get("accessory_allocations", []), demand_id=demand_id)
    total = Decimal(0)
    errors = []
    for device_id, amount in quantities.items():
        device = devices.get(device_id)
        if not device or device["variant_id"] not in rule["target_variant_ids"]:
            errors.append("已有配套分配引用了不匹配的设备")
            continue
        if amount > Decimal(device["quantity"]):
            errors.append("同一配套需求的分配合计超过设备数量，请调整关联")
            continue
        total += amount
    return total, errors


def incomplete_calculation(
    rule, demand_id, scope_id, status, errors, evidence, consumer_ids=None
):
    return demand_base(rule, demand_id, scope_id, consumer_ids or []) | {
        "status": status,
        "required": None,
        "existing": "0",
        "missing": None,
        "surplus": "0",
        "missing_information": errors,
        "evidence": evidence,
        "calculation": None,
    }


def unknown_scope(rule, device):
    result = incomplete_calculation(
        rule,
        digest([rule["id"], "unknown", device["id"]]),
        "unknown",
        "unknown",
        ["设备缺少计算范围所需的系统或房间归属"],
        [],
    )
    return result


def demand_base(rule, demand_id, scope_id, consumer_ids):
    return {
        "id": demand_id,
        "parent_id": scope_id,
        "scope": rule.get("calculation_scope"),
        "scope_id": scope_id,
        "need_key": rule.get("need_key") or rule["id"],
        "need_name": rule.get("need_name") or rule["name"],
        "consumer_requirement_ids": consumer_ids,
        "rule": rule,
    }


def consumer_requirement_ids(data, device_id):
    return [
        item["id"] for item in data["requirements"] if item.get("device_id") == device_id
    ]


def contribution_requirement_ids(contributions):
    return list(
        dict.fromkeys(
            item["requirement"]["id"]
            for item in contributions
            if item["requirement"].get("id")
        )
    )


def denial_rules(data, rule, variant):
    targets = set(rule["target_variant_ids"])
    return [
        item
        for item in data["knowledge_snapshot"]
        if item["kind"] == "accessory"
        and item["status"] == "confirmed"
        and item["effect"] == "deny"
        and targets & set(item["target_variant_ids"])
        and scope_matches(variant, item["selector"])
    ]


def cyclic_rule_ids(rules, variants):
    graph = defaultdict(set)
    owners = defaultdict(set)
    catalog = list(variants)
    for rule in rules:
        if rule["status"] != "confirmed" or rule["effect"] != "allow":
            continue
        sources = [item["id"] for item in catalog if scope_matches(item, rule["selector"])]
        for source in sources:
            for target in rule.get("target_variant_ids", []):
                graph[source].add(target)
                owners[(source, target)].add(rule["id"])
    cyclic = set()
    for source, targets in list(graph.items()):
        for target in targets:
            if reaches(graph, target, source, set()):
                cyclic.update(owners[(source, target)])
    return cyclic


def reaches(graph, current, target, visited):
    if current == target:
        return True
    if current in visited:
        return False
    next_visited = {*visited, current}
    return any(reaches(graph, item, target, next_visited) for item in graph.get(current, ()))
