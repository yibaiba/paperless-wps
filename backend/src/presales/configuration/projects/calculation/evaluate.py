from decimal import Decimal

from presales.rules.calculation import digest

from ...knowledge.semantics import candidate_check_v3, role_capabilities
from ..accessory_allocations import allocation_target_checks
from ..output import output_line
from ..readiness import project_readiness
from .context import prepare_demands, prepare_roles
from .coverage import coverage_checks
from .feature_choices import feature_checks
from .supply import supply_projection
from .usage import build_usage_projection
from .usage.checks import usage_checks
from .usage.models import PROJECTION_VERSION


def evaluate_v3(data, *, variants, catalog_variants, engine, definitions, decisions=None):
    from ..role_allocations import restore_requirement_ids
    from .role_allocations import allocation_checks

    input_data = data
    context = prepare_roles(data, definitions=definitions)
    data, aliases = context.data, context.aliases
    inspection_checks, inspection_policies = context.checks, context.policies
    systems = {s["id"]: s for s in data["systems"]}
    checks = compatibility(
        data, systems=systems, variants=variants, definitions=definitions, decisions=decisions
    )
    checks.extend(feature_checks(input_data, definitions))
    suggestions, included_checks = prepare_demands(
        context,
        variants=variants,
        catalog=catalog_variants,
        engine=engine,
        decisions=decisions,
    )
    checks.extend(included_checks)
    active = [s for s in suggestions if s["selected"]]
    checks.extend(allocation_target_checks(data, active))
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
    projection = build_usage_projection(
        data,
        demands=active,
        definitions=definitions,
        policies=policies,
        inspections=inspection_policies,
    )
    checks.extend(
        allocation_checks(
            input_data,
            definitions=definitions,
            engine=engine,
            fulfilled_ids=projection.fulfilled_ids,
        )
    )
    usages = projection.views()
    checks.extend(usage_checks(data, usages, variants=variants, decisions=decisions))
    resource_results = {}
    for check in checks:
        if check["kind"] == "capacity" and check.get("device_id"):
            resource_results.setdefault(check["device_id"], []).append(check)
    usages = [
        dict(u, resource_calculations=resource_results.get(u["device_id"], [])) for u in usages
    ]
    from .combinations import combination_checks

    checks.extend(
        combination_checks(
            data,
            variants=variants,
            suggestions=suggestions,
            definitions=definitions,
            engine=engine,
            decisions=decisions,
        )
    )
    supply, supply_checks = supply_projection(data)
    checks.extend(supply_checks)
    readiness = readiness_v3(input_data, checks, active, coverage)
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
    fingerprint = digest([PROJECTION_VERSION, business_input(input_data), suggestions, definitions])
    return restore_requirement_ids(
        dict(
            checks=checks,
            suggestions=suggestions,
            device_usages=usages,
            usage_projection=dict(version=projection.version, fingerprint=projection.fingerprint),
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
        ),
        aliases,
    )


def business_input(data):
    return {key: value for key, value in data.items() if key != "drawing_xml"}


def compatibility(data, *, systems, variants, definitions, decisions=None):
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
                knowledge_package_id=system.get("knowledge_package_id"),
                system_definition_id=system.get("definition_id", ""),
                capability_ids=role_capabilities(role_context, definitions),
            ),
            knowledge=data["knowledge_snapshot"],
            decisions=decisions,
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
    # Historical internal imports delegate to the current projection, never another kernel.
    return build_usage_projection(
        data,
        demands=suggestions,
        definitions={"definitions": [], "packages": []},
        policies=policies,
        inspections=inspection_policies,
    ).views()


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
