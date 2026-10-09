from ..catalog.service import CatalogService
from ..common import Entities
from .schemas import KnowledgeInput


def validate_knowledge(session, data):
    from ..definitions.service import Definitions
    from .evidence import validate_evidence_refs

    Definitions(session).validate_knowledge(data)
    catalog = CatalogService(session)
    catalog.validate_variant_ids(
        data.selector.variant_ids + data.selector.exclude_variant_ids + data.target_variant_ids
    )
    catalog.validate_variant_ids(data.reviewed_variant_ids)
    validate_evidence_refs(session, data.evidence_refs)
    _validate_combination(session, data)


def _validate_combination(session, data):
    if not data.combination:
        return
    catalog = CatalogService(session)
    for target in data.combination.targets:
        catalog.validate_variant_ids(target.variant_ids)
        if not target.system_definition_id:
            continue
        definition = Entities(session).get(
            target.system_definition_id, kind="system_definition"
        )
        role_ids = {role["id"] for role in definition.payload["roles"]}
        if target.role_id and target.role_id not in role_ids:
            raise ValueError("组合目标角色不属于所选系统定义")


def save_knowledge(session, data: KnowledgeInput, **options):
    validate_knowledge(session, data)
    if options.get("entity_id"):
        Entities(session).get(options["entity_id"], kind="knowledge")
    return Entities(session).save("knowledge", data, **options)
