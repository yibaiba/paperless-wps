from presales.application.idempotency import once

from ..catalog.service import CatalogService
from ..common import Entities
from ..definitions.service import Definitions
from ..knowledge.evidence import validate_evidence_refs


def case_revision(session, identity, revision):
    return Definitions(session).revision(identity, revision, kind="reference_case")


def save_case(session, request):
    def perform():
        for row in request.value.rows:
            validate_evidence_refs(session, row.evidence_refs)
            CatalogService(session).validate_variant_ids(row.variant_ids)
        return Entities(session).save(
            "reference_case",
            request.value,
            entity_id=request.case_id,
            expected_revision=request.expected_revision,
        )

    return once(session, namespace="reference-case-save", request=request, perform=perform)


def link_case(session, configuration, reference):
    if reference is None:
        return dict(configuration, reference_case=None)
    case = case_revision(session, reference.id, reference.revision)
    row_ids = {r["id"] for r in case["rows"]}
    devices = {d["id"] for d in configuration["devices"]}
    roles = {r["id"] for r in configuration["requirements"]}
    included = {a["id"] for a in configuration.get("included_allocations", [])}
    features = (
        system_features(session, configuration)
        if any(b.disposition == "not_enabled" for b in reference.bindings)
        else {}
    )
    for binding in reference.bindings:
        if binding.row_id not in row_ids:
            raise ValueError("案例行不属于此固定修订")
        if set(binding.device_ids) - devices or set(binding.requirement_ids) - roles:
            raise ValueError("案例映射引用的设备或需求不存在")
        if set(binding.included_allocation_ids) - included:
            raise ValueError("案例映射引用的已含抵扣不存在")
        if binding.disposition == "not_enabled":
            systems = {s["id"]: s for s in configuration["systems"]}
            system = systems.get(binding.feature_system_id)
            if not system or not binding.feature:
                raise ValueError("未启用功能结论需要对应系统和功能")
            if binding.feature not in features.get(system["id"], set()):
                raise ValueError("功能名称不属于该系统固定资料定义，保留待确认而非未启用")
            if system["id"] not in configuration.get("generation", {}).get(
                "features_confirmed", []
            ):
                raise ValueError("请先明确确认该系统的功能选择")
            if binding.feature in system["features"]:
                raise ValueError("功能仍已启用，不能标记未启用")
    return dict(configuration, reference_case=reference.model_dump(mode="json"))


def validate_reference(session, reference):
    if reference is None:
        return
    case = case_revision(session, reference.id, reference.revision)
    rows = {r["id"] for r in case["rows"]}
    if any(b.row_id not in rows for b in reference.bindings):
        raise ValueError("案例映射的行不属于固定资料修订")


def system_features(session, configuration):
    from ..definitions.requirements import definitions_for

    fixed = definitions_for(session, configuration.get("definition_snapshot_id"))
    definitions = {d["id"]: d for d in fixed["definitions"]}
    packages = {p["id"]: p for p in fixed["packages"]}
    result = {}
    for system in configuration["systems"]:
        package = packages.get(system.get("knowledge_package_id"))
        definition = (
            package["definition"] if package else definitions.get(system.get("definition_id"))
        )
        result[system["id"]] = {
            r["feature"] for r in (definition or {}).get("roles", []) if r["feature"]
        }
    return result
