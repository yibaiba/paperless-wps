"""Synthetic evidence verifies explicit association without publishing business knowledge."""

from copy import deepcopy

import pytest
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.common import Entities, view
from presales.configuration.definitions.gaps import knowledge_gaps
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import SourceLink
from presales.rules.repository import RuleConflict
from presales.storage import Base, CatalogImport, ProductRecord
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .booking_mapping import SYSTEM, MappingSelection, build_mapping_plan
from .maintenance import apply_plan

AUTHOR = dict(actor="隔离映射测试", evidence="合成测试原文，不作为真实搭配依据")


@pytest.fixture
def case():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, seed(session)
    engine.dispose()


def seed(session):
    entities, definitions = Entities(session), Definitions(session)
    session.add(
        CatalogImport(
            id="i",
            filename="isolated.xlsx",
            digest="test",
            sheets=[],
            record_count=1,
            issue_count=0,
        )
    )
    product = entities.save("product", ProductInput(name="合成软件", model="CRIR-GL20S", **AUTHOR))
    variant = entities.save(
        "variant", VariantInput(product_id=product["id"], name="测试配置", **AUTHOR)
    )
    session.add(
        ProductRecord(
            id="source",
            import_id="i",
            name="合成软件",
            model="CRIR-GL20S",
            sheet="会议预约与信发系统",
            payload=dict(row=18, specification="Linux"),
        )
    )
    session.flush()
    session.add(SourceLink(source_id="source", variant_id=variant["id"], **AUTHOR))
    definition = definitions.save_definition(
        SystemDefinition(
            name=SYSTEM, roles=[dict(id="server-software", name="服务端软件")], **AUTHOR
        )
    )
    rule = entities.save(
        "knowledge",
        KnowledgeInput(
            name="隔离旧文字关系",
            kind="suitability",
            status="confirmed",
            system="会议预约",
            role="服务端软件",
            selector=dict(variant_ids=[variant["id"]]),
            conditions=[dict(field="project.os", operator="eq", value="Linux")],
            evidence_refs=[dict(source_id="source", locator="测试F18", quote="Linux")],
            **AUTHOR,
        ),
    )
    package = definitions.save_package(
        KnowledgePackage(
            name="隔离资料包",
            branch="预约",
            system_definition_id=definition["id"],
            definition_revision=1,
            members=[dict(id=rule["id"], revision=1)],
            **AUTHOR,
        )
    )
    session.commit()
    return MappingSelection(rule_id=rule["id"], package_id=package["id"], source_id="source")


def test_explicit_mapping_preserves_conditions_status_and_fixed_history(case):
    session, selected = case
    entities = Entities(session)
    original = deepcopy(entities.get(selected.rule_id).payload)
    package = deepcopy(view(entities.get(selected.package_id)))
    assert any(
        g["code"] == "relation_role_unmapped"
        for g in knowledge_gaps(package["definition"], package)
    )
    plan = build_mapping_plan(session, selected)
    assert len(apply_plan(session, plan)) == 2
    session.commit()
    rule = entities.get(selected.rule_id).payload
    updated = view(entities.get(selected.package_id))
    for key in (
        "conditions",
        "activation_conditions",
        "selector",
        "status",
        "quantity_review",
        "factor",
        "evidence_refs",
    ):
        assert rule[key] == original[key]
    assert updated["status"] == "draft"
    assert updated["definition"] == package["definition"]
    assert not any(
        g["code"] == "relation_role_unmapped"
        for g in knowledge_gaps(updated["definition"], updated)
    )
    assert entities.history(selected.rule_id)[-1]["system_definition_id"] == ""
    assert entities.history(selected.package_id)[-1]["members"] == package["members"]
    assert apply_plan(session, plan) == []
    assert apply_plan(session, build_mapping_plan(session, selected)) == []


def test_replay_preserves_later_maintenance_and_does_not_adopt_new_rules(case):
    session, selected = case
    apply_plan(session, build_mapping_plan(session, selected))
    entities = Entities(session)
    record = entities.get(selected.rule_id)
    entities.save(
        "knowledge",
        dict(record.payload, status="draft", evidence="后续维护者待核对"),
        entity_id=record.id,
        expected_revision=record.revision,
    )
    before = deepcopy(entities.get(selected.package_id).payload)
    session.commit()
    assert apply_plan(session, build_mapping_plan(session, selected)) == []
    assert entities.get(selected.package_id).payload == before
    assert entities.get(selected.rule_id).payload["status"] == "draft"


def test_source_change_rejects_prepared_mapping_without_partial_write(case):
    session, selected = case
    plan = build_mapping_plan(session, selected)
    source = session.get(ProductRecord, selected.source_id)
    source.payload = dict(source.payload, specification="new source")
    session.flush()
    with pytest.raises(RuleConflict, match="依据已变化"):
        apply_plan(session, plan)
    assert Entities(session).get(selected.rule_id).revision == 1


def test_stale_package_rejects_batch_before_mapping_is_written(case):
    session, selected = case
    plan = build_mapping_plan(session, selected)
    entities = Entities(session)
    package = entities.get(selected.package_id)
    entities.save(
        "knowledge_package",
        dict(package.payload, evidence="后续包修改"),
        entity_id=package.id,
        expected_revision=1,
    )
    with pytest.raises(RuleConflict, match="预览版本过期"):
        apply_plan(session, plan)
    assert entities.get(selected.rule_id).revision == 1


def test_published_package_is_not_automatically_changed(case):
    session, selected = case
    entities = Entities(session)
    package = entities.get(selected.package_id)
    entities.save(
        "knowledge_package",
        dict(package.payload, status="published"),
        entity_id=package.id,
        expected_revision=1,
    )
    with pytest.raises(ValueError, match="只维护草稿"):
        build_mapping_plan(session, selected)
    assert entities.get(selected.rule_id).revision == 1


def test_explicit_other_mapping_is_never_overwritten(case):
    session, selected = case
    entities = Entities(session)
    rule = entities.get(selected.rule_id)
    entities.save(
        "knowledge",
        dict(rule.payload, system_definition_id="other"),
        entity_id=rule.id,
        expected_revision=1,
    )
    with pytest.raises(ValueError, match="已有其他明确映射"):
        build_mapping_plan(session, selected)
