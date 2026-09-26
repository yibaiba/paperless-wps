from presales.rules.calculation import digest

from ..knowledge.evaluator import candidate_check
from .accessories import accessory_suggestions
from .accessory_allocations import accessory_allocation_checks, prune_stale_allocations
from .device_usages import build_device_usages, device_usage_checks
from .output import project_output
from .readiness import project_readiness


def evaluate_configuration(data, *, variants, catalog_variants, engine):
    knowledge = data["knowledge_snapshot"]
    systems = {item["id"]: item for item in data["systems"]}
    devices = {item["id"]: item for item in data["devices"]}
    requirements = [
        {**item, "system": systems[item["system_id"]]["kind"]}
        for item in data["requirements"]
    ]
    checks = compatibility_checks(
        requirements,
        devices=devices,
        variants=variants,
        knowledge=knowledge,
    )
    suggestions = accessory_suggestions(
        data, variants=variants, catalog_variants=catalog_variants, engine=engine
    )
    if data.get("calculation_version", 1) >= 2:
        checks.extend(prune_stale_allocations(data, suggestions))
        checks.extend(accessory_allocation_checks(data, suggestions))
    usages = build_device_usages(data, suggestions)
    usages_by_device = {item["device_id"]: item for item in usages}
    for device in devices.values():
        checks.extend(
            device_usage_checks(
                device,
                usages_by_device[device["id"]],
                variant=variants[device["id"]],
                knowledge=knowledge,
            )
        )
    readiness = project_readiness(data, checks, suggestions)
    return {
        "checks": checks,
        "suggestions": suggestions,
        "device_usages": usages,
        "readiness": readiness,
        "project_output": project_output(data, usages, readiness),
        "fingerprint": digest(
            [{key: value for key, value in data.items() if key != "drawing_xml"}, suggestions]
        ),
        "versions": [
            {"id": item["id"], "revision": item["revision"]} for item in knowledge
        ],
        "calculation_version": data.get("calculation_version", 1),
    }


def compatibility_checks(requirements, *, devices, variants, knowledge):
    checks = []
    for requirement in requirements:
        device = devices.get(requirement["device_id"])
        if device is None:
            checks.append(
                {
                    "kind": "selection",
                    "requirement_id": requirement["id"],
                    "status": "unknown",
                    "message": "尚未选择设备",
                }
            )
            continue
        result = candidate_check(
            variants[device["id"]], requirement=requirement, knowledge=knowledge
        )
        checks.append(
            {
                "kind": "compatibility",
                "requirement_id": requirement["id"],
                "device_id": device["id"],
                "status": result["status"],
                "evidence": result["evidence"],
            }
        )
    return checks
