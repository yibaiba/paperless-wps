from decimal import Decimal

from presales.rules.calculation import digest

from ...knowledge.evaluator import context_for, scope_matches
from ...knowledge.semantics import (
    candidate_check_v3,
    evaluate_rules_v3,
    role_capabilities,
    scope_is_reviewed,
)
from ..accessory_allocations import accessory_allocation_checks
from ..device_usages import build_device_usages, capacity_checks, unique_consumers
from ..output import output_line
from ..readiness import project_readiness
from .coverage import coverage_checks
from .demands import accessory_demands_v3
from .inspections import prepare_inspections
from .resource_review import resource_policy_checks
from .supply import supply_projection


def evaluate_v3(data, *, variants, catalog_variants, engine, definitions):
    input_data = data
    data, inspection_checks, inspection_policies = prepare_inspections(data, definitions)
    systems = {s["id"]: s for s in data["systems"]}
    checks = compatibility(data, systems=systems, variants=variants, definitions=definitions)
    suggestions = accessory_demands_v3(
        data, variants=variants, catalog_variants=catalog_variants, engine=engine
    )
    active = [s for s in suggestions if s["selected"]]
    checks.extend(accessory_allocation_checks(data, active))
    checks.extend(selection_checks(suggestions))
    coverage, policies = coverage_checks(data, definitions, variants, demands=active)
    checks.extend(coverage)
    checks.extend(inspection_checks)
    for identity, review in inspection_policies.items():
        previous = policies.get(identity, "unknown")
        if previous != "unknown" and previous != review["selected"]:
            checks.append(
                dict(
                    kind="inspection",
                    status="conflict",
                    requirement_id=identity,
                    message="知识包与用途检查的容量适用结论不一致，请核对修订",
                )
            )
        policies[identity] = review["selected"]
    usages = resource_usages(data, active, policies, inspection_policies=inspection_policies)
    checks.extend(usage_checks(data, usages, variants=variants))
    supply, supply_checks = supply_projection(data)
    checks.extend(supply_checks)
    readiness = readiness_v3(data, checks, active, coverage)
    usages_by_device = {u["device_id"]: u for u in usages}
    lines = [
        dict(output_line(d, usages_by_device.get(d["id"])), supply=supply[d["id"]])
        for d in data["devices"]
    ]
    procurement = [
        dict(line, quantity=line["supply"]["purchase"])
        for line in lines
        if Decimal(line["supply"]["purchase"]) > 0
    ]
    fingerprint = digest([business_input(input_data), suggestions, definitions])
    return dict(
        checks=checks,
        suggestions=suggestions,
        device_usages=usages,
        readiness=readiness,
        project_output=dict(
            status="draft",
            ready_for_confirmed_output=False,
            ready_for_confirmation=readiness["ready_for_confirmation"],
            knowledge_snapshot_id=data["knowledge_snapshot_id"],
            calculation_version=3,
            lines=lines,
            procurement_lines=procurement,
        ),
        fingerprint=fingerprint,
        versions=[dict(id=k["id"], revision=k["revision"]) for k in data["knowledge_snapshot"]],
        calculation_version=3,
    )


def business_input(data):
    return {key: value for key, value in data.items() if key != "drawing_xml"}


def compatibility(data, *, systems, variants, definitions):
    checks = []
    for requirement in data["requirements"]:
        device_id = requirement.get("device_id")
        if device_id not in variants:
            checks.append(
                dict(
                    kind="selection",
                    status="unknown",
                    requirement_id=requirement["id"],
                    message="尚未选择设备",
                )
            )
            continue
        system = systems[requirement["system_id"]]
        role_context = dict(
            requirement,
            system_definition_id=system.get("definition_id"),
            knowledge_package_id=system.get("knowledge_package_id"),
        )
        result = candidate_check_v3(
            variants[device_id],
            requirement=dict(
                requirement,
                system=system["kind"],
                system_definition_id=system.get("definition_id", ""),
                capability_ids=role_capabilities(role_context, definitions),
            ),
            knowledge=data["knowledge_snapshot"],
        )
        checks.append(
            dict(
                kind="compatibility",
                status=result["status"],
                device_id=device_id,
                requirement_id=requirement["id"],
                evidence=result["evidence"],
            )
        )
    return checks


def selection_checks(suggestions):
    return [
        dict(
            kind="accessory_choice",
            status="conflict",
            demand_id=s["id"],
            message="已取消选用但仍有关联配套，请在变更预览中移除关联",
        )
        for s in suggestions
        if s["selection_conflict"]
    ]


def resource_usages(data, suggestions, policies, *, inspection_policies=None):
    usages = build_device_usages(data, suggestions)
    rules = {s["id"]: s["rule"] for s in suggestions}
    for usage in usages:
        for consumer in usage["consumers"]:
            policy = (
                policies.get(consumer["requirement_id"], "unknown")
                if consumer["via"] == "direct"
                else rules[consumer["demand_id"]].get("resource_policy", "unknown")
            )
            review = (inspection_policies or {}).get(consumer["requirement_id"], {})
            if consumer["via"] == "accessory" and rules[consumer["demand_id"]][
                "need_key"
            ] in review.get("needs", set()):
                consumer["inspection_policy_conflict"] = policy == "not_applicable"
                policy = "required"
            consumer["capacity_expected"] = (
                bool(consumer["resources"]) or policy != "not_applicable"
            )
            consumer["resource_policy"] = policy
            consumer["resource_rule_revision"] = (
                rules[consumer["demand_id"]]["revision"] if consumer["via"] == "accessory" else None
            )
            consumer["resource_rule_id"] = (
                rules[consumer["demand_id"]]["id"] if consumer["via"] == "accessory" else None
            )
    return usages


def usage_checks(data, usages, *, variants):
    devices = {d["id"]: d for d in data["devices"]}
    checks = []
    for usage in usages:
        device = devices[usage["device_id"]]
        checks.extend(resource_policy_checks(usage))
        checks.extend(
            dict(
                kind="inspection",
                status="conflict",
                device_id=device["id"],
                requirement_id=c["requirement_id"],
                rule_id=c["resource_rule_id"],
                rule_revision=c["resource_rule_revision"],
                message="配套关系标记无需容量检查，但用途检查指定了资源需求，请核对依据",
            )
            for c in usage["consumers"]
            if c.get("inspection_policy_conflict")
        )
        # Unknown applicability is a knowledge task, not a missing project value.
        consumers = unique_consumers(
            [
                dict(
                    c, capacity_expected=bool(c["resources"]) or c["resource_policy"] == "required"
                )
                for c in usage["consumers"]
            ]
        )
        checks.extend(
            capacity_checks(device, consumers, variant=variants[device["id"]], usage=usage)
        )
        if len(consumers) > 1:
            checks.append(sharing(data, device, consumers, variant=variants[device["id"]]))
    return checks


def sharing(data, device, consumers, *, variant):
    requirements = {r["id"]: r for r in data["requirements"]}
    systems = {s["id"]: s for s in data["systems"]}
    ids = {
        (
            systems[c["system_id"]].get("definition_id"),
            requirements[c["requirement_id"]].get("role_id"),
        )
        for c in consumers
    }
    names = {c["system"] + "/" + c["role"] for c in consumers}
    rules = [
        r
        for r in data["knowledge_snapshot"]
        if r["kind"] == "sharing"
        and r["status"] == "confirmed"
        and scope_matches(variant, r["selector"])
        and (
            ids <= {(s["system_definition_id"], s["role_id"]) for s in r["shared_role_refs"]}
            if r.get("shared_role_refs")
            else names <= set(r["shared_roles"])
        )
    ]
    results = [evaluate_rules_v3(rules, context_for(variant, c["environment"])) for c in consumers]
    states = {r["status"] for r in results}
    status = "conflict" if "conflict" in states else "unknown" if "unknown" in states else "pass"
    if status == "pass" and any(not scope_is_reviewed(r, variant) for r in rules):
        status = "unknown"
    if Decimal(device["quantity"]) != 1:
        status = "conflict"
    return dict(
        kind="sharing",
        device_id=device["id"],
        status=status,
        message="缺少已确认共用依据" if not rules else "按设备实例核对共享条件",
        evidence=[e for r in results for e in r["evidence"]],
    )


def readiness_v3(data, checks, active, coverage):
    result = project_readiness(data, checks, active)
    ready = result["ready_for_confirmed_output"]
    return dict(
        result,
        ready_for_confirmed_output=False,
        ready_for_confirmation=ready,
        known_checks=combine_status([c for c in checks if c["kind"] != "coverage"]),
        coverage=combine_status(coverage),
        stages=[
            dict(s, message="已满足确认条件，请保存后确认该版本")
            if s["key"] == "output" and ready
            else s
            for s in result["stages"]
        ],
    )


def combine_status(checks):
    states = {c["status"] for c in checks}
    return (
        "conflict"
        if "conflict" in states
        else "unknown"
        if not states or "unknown" in states
        else "pass"
    )
