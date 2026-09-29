from uuid import NAMESPACE_URL, uuid5

from presales.configuration.catalog.schemas import LinkInput, ProductInput, VariantInput
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.knowledge.routes import save as save_knowledge
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import SourceLink

from .impacts import affected


def stable_id(batch_id, row_id, kind):
    return str(uuid5(NAMESPACE_URL, f"catalog-update:{batch_id}:{row_id}:{kind}"))


def apply_product(session, *, row, decision, batch_id):
    catalog = CatalogService(session)
    if decision.action == "defer":
        return None
    current = catalog.variants(ids=[decision.variant_id]) if decision.variant_id else []
    variant = current[0] if current else None
    if decision.action in {"new_variant", "new_product"}:
        variant = create_variant(session, row=row, decision=decision, batch_id=batch_id)
    elif decision.action in {"display", "correct", "supply"}:
        variant = revise_variant(session, variant=variant, decision=decision)
    if variant is None:
        raise ValueError("请明确选择配置")
    source = row.get("source")
    if not source and decision.action in {"new_variant", "new_product"}:
        from .manual_sources import create_manual_source

        source = create_manual_source(
            session,
            variant=variant,
            decision=decision,
            update_batch_id=batch_id,
            identities=(
                stable_id(batch_id, row["id"], "manual-batch"),
                stable_id(batch_id, row["id"], "manual-source"),
            ),
        )
    if source:
        link = session.get(SourceLink, source["id"])
        if link and link.variant_id != variant["id"]:
            raise ValueError("该来源已关联其他配置，请先核对来源归属")
        if not link:
            catalog.link(
                LinkInput(
                    variant_id=variant["id"],
                    items=[dict(source_id=source["id"], expected_revision=0)],
                    actor=decision.actor,
                    evidence=decision.evidence,
                )
            )
    return variant


def create_variant(session, *, row, decision, batch_id):
    catalog, entities = CatalogService(session), Entities(session)
    if decision.variant is None:
        raise ValueError("新增配置需要填写完整配置资料")
    values = decision.variant.model_dump(mode="json")
    values.update(
        actor=decision.actor,
        evidence=decision.evidence,
        status="confirmed",
        review_requirements=[dict(id="new_configuration", name="新配置适用范围待核对")],
    )
    values["included_items"] = [
        dict(item, status="draft") for item in values.get("included_items", [])
    ]
    if decision.action == "new_product":
        if decision.product is None:
            raise ValueError("新增产品需要填写产品身份")
        product = catalog.save_product(
            ProductInput.model_validate(
                {
                    **decision.product.model_dump(),
                    "actor": decision.actor,
                    "evidence": decision.evidence,
                }
            ),
            create_id=stable_id(batch_id, row["id"], "product"),
        )
        values["product_id"] = product["id"]
    variant = catalog.save_variant(
        VariantInput.model_validate(values), create_id=stable_id(batch_id, row["id"], "variant")
    )
    impact = affected(session, CatalogService(session).variants(ids=[variant["id"]])[0])
    if impact["rules"]:
        values["review_requirements"] = impact["rules"]
        variant = catalog.save_variant(
            VariantInput.model_validate(values),
            entity_id=variant["id"],
            expected_revision=variant["revision"],
        )
    for identity in decision.copy_rule_ids:
        old = entities.get(identity, kind="knowledge").payload
        fields = dict(
            old,
            name=old["name"] + "（新配置待核对）",
            status="draft",
            schema_version=2,
            quantity_review="unreviewed",
            reviewed_variant_ids=[],
            scope_basis="listed_configurations",
            actor=decision.actor,
            evidence=decision.evidence + "；复制原关系：" + identity,
            selector=dict(
                variant_ids=[variant["id"]], category="", series=[], exclude_variant_ids=[]
            ),
        )
        save_knowledge(session, KnowledgeInput.model_validate(fields))
    return variant


def revise_variant(session, *, variant, decision):
    if not variant or variant["revision"] != decision.expected_variant_revision:
        from presales.rules.repository import RuleConflict

        raise RuleConflict("产品配置已有新修订，请重新核对")
    fields = VariantInput.model_validate(
        {k: v for k, v in variant.items() if k in VariantInput.model_fields}
    ).model_dump(mode="json")
    if decision.action == "supply":
        if not decision.supply_status:
            raise ValueError("请选择供货状态")
        fields.update(supply_status=decision.supply_status, replacements=decision.replacements)
    else:
        if decision.variant is None:
            raise ValueError("请填写修改后的配置")
        incoming = decision.variant.model_dump(mode="json")
        if decision.action == "display":
            fields.update({key: incoming[key] for key in ("name", "description")})
        else:
            if incoming["product_id"] != variant["product_id"]:
                raise ValueError("修正原配置不能更换产品身份，请新增配置")
            fields.update(incoming)
    fields.update(actor=decision.actor, evidence=decision.evidence)
    return CatalogService(session).save_variant(
        VariantInput.model_validate(fields),
        entity_id=variant["id"],
        expected_revision=variant["revision"],
    )
