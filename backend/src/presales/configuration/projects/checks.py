from collections import defaultdict
from decimal import Decimal

from presales.rules.calculation import digest

from ..knowledge.evaluator import candidate_check, context_for, evaluate_rules, scope_matches
from .accessories import accessory_suggestions
from .accessory_allocations import accessory_allocation_checks


def sharing_checks(device, requirements, *, variant, knowledge):
    if not requirements:
        return []
    roles = {r["system"] + "/" + r["role"] for r in requirements}
    rules = [
        k
        for k in knowledge
        if k["kind"] == "sharing"
        and k["status"] == "confirmed"
        and roles <= set(k["shared_roles"])
        and scope_matches(variant, k["selector"])
    ]
    checks = []
    for requirement in requirements if len(requirements) > 1 else []:
        result = evaluate_rules(rules, context_for(variant, requirement["environment"]))
        checks.append(
            dict(kind="sharing", device_id=device["id"], requirement_id=requirement["id"], **result)
        )
    demands = defaultdict(Decimal)
    for requirement in requirements:
        for resource in requirement["resources"]:
            demands[(resource["key"], resource["unit"])] += Decimal(resource["amount"])
    attributes = {a["key"]: a for a in variant["attributes"]}
    if not demands or any(not r["resources"] for r in requirements):
        checks.append(
            dict(
                kind="capacity",
                device_id=device["id"],
                status="unknown",
                message="缺少部分角色的资源需求，未完成容量验证",
            )
        )
    for (key, unit), required in demands.items():
        capacity = attributes.get(key)
        known = (
            capacity
            and capacity["kind"] in {"number", "quantity"}
            and capacity["value"] is not None
            and capacity["unit"] == unit
        )
        status = "unknown"
        if known:
            status = "pass" if Decimal(str(capacity["value"])) >= required else "conflict"
        checks.append(
            dict(
                kind="capacity",
                device_id=device["id"],
                status=status,
                resource=key,
                unit=unit,
                required=str(required),
                capacity=capacity["value"] if known else None,
            )
        )
    return checks


def evaluate_configuration(data, *, variants, engine):
    knowledge = data["knowledge_snapshot"]
    systems = {s["id"]: s for s in data["systems"]}
    devices = {d["id"]: d for d in data["devices"]}
    requirements = [{**r, "system": systems[r["system_id"]]["kind"]} for r in data["requirements"]]
    checks = []
    for requirement in requirements:
        device = devices.get(requirement["device_id"])
        if device is None:
            checks.append(
                dict(
                    kind="selection",
                    requirement_id=requirement["id"],
                    status="unknown",
                    message="尚未选择设备",
                )
            )
            continue
        result = candidate_check(
            variants[device["id"]], requirement=requirement, knowledge=knowledge
        )
        checks.append(
            dict(
                kind="compatibility",
                requirement_id=requirement["id"],
                device_id=device["id"],
                status=result["status"],
                evidence=result["evidence"],
            )
        )
    for device in devices.values():
        served = [r for r in requirements if r["device_id"] == device["id"]]
        checks.extend(
            sharing_checks(device, served, variant=variants[device["id"]], knowledge=knowledge)
        )
    suggestions = accessory_suggestions(data, variants=variants, engine=engine)
    if data.get("calculation_version", 1) >= 2:
        checks.extend(accessory_allocation_checks(data, suggestions))
    return dict(
        checks=checks,
        suggestions=suggestions,
        fingerprint=digest([{k: v for k, v in data.items() if k != "drawing_xml"}, suggestions]),
        versions=[dict(id=k["id"], revision=k["revision"]) for k in knowledge],
        calculation_version=data.get("calculation_version", 1),
    )
