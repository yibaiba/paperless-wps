from ..catalog.service import CatalogService
from ..common import Entities
from ..definitions.service import Definitions
from ..knowledge.evaluator import candidate_check, scope_matches
from ..knowledge.semantics import candidate_check_v3, role_capabilities, role_matches
from .knowledge_snapshot import candidate_knowledge

STATUS_ORDER = {"pass": 0, "unknown": 1, "conflict": 2}


def candidate_results(data, *, session, search=None, catalog=None):
    knowledge = candidate_knowledge(session, data.knowledge_snapshot_id)
    definitions = (
        (
            Entities(session).get(data.definition_snapshot_id, kind="definition_snapshot").payload
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
    if data.calculation_version < 3 and any(
        r.get("schema_version", 1) > 1 and role_matches(r, requirement) for r in knowledge
    ):
        raise ValueError("当前角色包含新版知识，请预览并升级项目计算语义至版本 3")
    checked = [
        {
            **evaluator(v, requirement=requirement, knowledge=knowledge),
            "ranking": ranking.get(v["id"]),
        }
        for v in variants
    ]
    for item in checked:
        variant = item["variant"]
        from presales.catalog_updates.impacts import pending_reviews

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
    return [
        variant
        for variant in variants
        if (capabilities and set(capabilities) <= set(variant.get("capability_ids", [])))
        or any(
            item["kind"] == "suitability"
            and item["status"] != "disabled"
            and role_matches(item, data.model_dump(mode="json"))
            and scope_matches(variant, item["selector"])
            for item in knowledge
        )
    ]
