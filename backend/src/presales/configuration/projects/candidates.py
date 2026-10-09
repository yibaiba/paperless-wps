from ..catalog.service import CatalogService
from ..common import Entities
from ..definitions.service import Definitions
from ..knowledge.evaluator import candidate_check, scope_matches
from ..knowledge.semantics import candidate_check_v3, role_capabilities, role_matches
from .knowledge_snapshot import candidate_knowledge

STATUS_ORDER = {"pass": 0, "unknown": 1, "conflict": 2}


def candidate_results(data, *, session, search=None, catalog=None, decisions=None, engine=None):
    decisions = decisions.request() if decisions else None
    projector = None
    if data.configuration is not None and data.calculation_version == 3:
        from .repository import ProjectConfigurations
        from .services.candidate_combinations import CandidateCombinations

        if engine is None:
            raise ValueError("项目候选数量计算服务未配置")
        projector = CandidateCombinations(
            ProjectConfigurations(session, engine, catalog=catalog), data
        )
        knowledge, definitions = projector.data["knowledge_snapshot"], projector.definitions
        decisions = projector.decisions
        requirement = dict(data.model_dump(mode="json"), environment=projector.role["environment"])
    else:
        knowledge = candidate_knowledge(session, data.knowledge_snapshot_id)
        definitions = (
            (
                Entities(session)
                .get(data.definition_snapshot_id, kind="definition_snapshot")
                .payload
                if data.definition_snapshot_id
                else Definitions(session).current_snapshot()
            )
            if data.calculation_version == 3
            else {"definitions": [], "packages": []}
        )
        requirement = data.model_dump(mode="json")
        requirement["capability_ids"] = role_capabilities(requirement, definitions)
        if data.calculation_version == 3 and data.knowledge_package_id:
            from .services.definition_snapshot import project_knowledge

            knowledge = project_knowledge(
                dict(
                    knowledge_snapshot=knowledge,
                    systems=[
                        dict(
                            definition_id=data.system_definition_id,
                            knowledge_package_id=data.knowledge_package_id,
                        )
                    ],
                ),
                definitions,
            )
    requirement["capability_ids"] = role_capabilities(requirement, definitions)
    variants = (catalog if catalog is not None else CatalogService(session)).variants()
    if not data.system.strip() or not data.role.strip():
        # Explicit catalog browsing has no role context to establish suitability.
        return [dict(variant=v, status="unknown", evidence=[], ranking=None) for v in variants]
    ranking = {}
    mode = "all" if data.include_all else data.mode
    if mode == "known":
        variants = _known_variants(
            variants, knowledge=knowledge, data=data, capabilities=requirement["capability_ids"]
        )
    elif mode == "semantic":
        if search is None:
            raise ValueError("语义搜索服务未配置")
        results = search.search(_semantic_query(data), variants, limit=data.limit)
        ranking = {item["variant_id"]: item for item in results}
        variants = [variant for variant in variants if variant["id"] in ranking]
    evaluator = candidate_check_v3 if data.calculation_version == 3 else candidate_check
    options = {}
    if data.decision_runtime == "zen-v1":
        if data.calculation_version != 3 or decisions is None:
            raise ValueError("ZEN 决策服务未配置或计算语义不匹配")
        if data.decision_bundle_id and projector is None:
            from .services.candidate_versions import validate_bundle

            validate_bundle(data, knowledge=knowledge, session=session, decisions=decisions)
        options["decisions"] = decisions
    if data.calculation_version < 3 and any(
        r.get("schema_version", 1) > 1 and role_matches(r, requirement) for r in knowledge
    ):
        raise ValueError("当前角色包含新版知识，请预览并升级项目计算语义至版本 3")
    checked = [
        {
            **evaluator(v, requirement=requirement, knowledge=knowledge, **options),
            "ranking": ranking.get(v["id"]),
        }
        for v in variants
    ]
    if projector is not None:
        checked = [projector.check(item) for item in checked]
        for item in checked:
            item["input_checks"] = projector.input_checks
            states = {c["status"] for c in projector.input_checks} | {item["status"]}
            item["status"] = (
                "conflict" if "conflict" in states else "unknown" if "unknown" in states else "pass"
            )
    for item in checked:
        variant = item["variant"]
        from ..catalog.impacts import pending_reviews

        reviews = pending_reviews(variant, knowledge, uses=[requirement])
        if reviews and item["status"] == "pass":
            item["status"] = "unknown"
            item["catalog_review"] = reviews
        if variant.get("supply_status", "available") != "available":
            item["status"] = "conflict"
            item["supply_message"] = "此配置已停止选用，历史引用保留"
    return sorted(
        checked,
        key=lambda item: (
            STATUS_ORDER[item["status"]],
            item["ranking"]["rank"] if item["ranking"] else 0,
        ),
    )


def _semantic_query(data):
    environment = "、".join(f"{item.key}={item.value}{item.unit}" for item in data.environment)
    parts = [f"系统：{data.system}", f"角色：{data.role}", f"需求：{data.query_text}"]
    if environment:
        parts.append("环境：" + environment)
    return "\n".join(parts)


def _known_variants(variants, *, knowledge, data, capabilities=()):
    requirement = data.model_dump(mode="json")
    relevant = [
        item
        for item in knowledge
        if item["kind"] == "suitability"
        and item["status"] != "disabled"
        and role_matches(item, requirement)
    ]
    return [
        variant
        for variant in variants
        if (capabilities and set(capabilities) <= set(variant.get("capability_ids", [])))
        or any(scope_matches(variant, item["selector"]) for item in relevant)
    ]
