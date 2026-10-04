"""Synthetic sources verify maintenance mechanics, never business compatibility."""

from copy import deepcopy
from uuid import uuid4

import pytest
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import SourceLink
from presales.storage import Base, CatalogImport, ProductRecord
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .distributed import build_distributed_plan
from .distributed_specs import DISTRIBUTED, MARKER, ROLES
from .maintenance import apply_plan

AUTHOR = dict(actor="隔离测试", evidence="合成资料，只验证软件行为")


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed(session)
        yield session
    engine.dispose()


def seed(session):
    entities = Entities(session)
    session.add(
        CatalogImport(
            id="i",
            filename="test.xlsx",
            digest="isolated",
            sheets=[DISTRIBUTED],
            record_count=11,
            issue_count=0,
        )
    )
    session.flush()
    for spec in ROLES:
        if spec.row is None:
            continue
        product = entities.save(
            "product", ProductInput(name=spec.name, model="TEST-" + str(spec.row), **AUTHOR)
        )
        variant = entities.save(
            "variant", VariantInput(product_id=product["id"], name=spec.name, **AUTHOR)
        )
        text = "必搭配显示和扩声设备使用" if spec.row == 65 else "隔离参数"
        session.add(
            ProductRecord(
                id=str(spec.row),
                import_id="i",
                name=spec.name,
                model=product["model"],
                sheet=DISTRIBUTED,
                payload=dict(row=spec.row, specification=text, note=text, prices={}),
            )
        )
        session.flush()
        session.add(SourceLink(source_id=str(spec.row), variant_id=variant["id"], **AUTHOR))
    definition = Definitions(session).save_definition(
        SystemDefinition(
            name=DISTRIBUTED,
            roles=[dict(id=str(uuid4()), name=s.name, required=False) for s in ROLES],
            **AUTHOR,
        )
    )
    product_rule = entities.save(
        "knowledge",
        KnowledgeInput(
            name="已有文字关系",
            kind="suitability",
            selector=dict(category="测试"),
            system=DISTRIBUTED,
            role="客户端软件",
            **AUTHOR,
        ),
    )
    Definitions(session).save_package(
        KnowledgePackage(
            name="隔离分布式资料包",
            branch="待核对",
            system_definition_id=definition["id"],
            definition_revision=definition["revision"],
            members=[dict(id=product_rule["id"], revision=product_rule["revision"])],
            **AUTHOR,
        )
    )
    session.commit()


def test_source_maintenance_is_idempotent_and_never_confirms_unknown_counts(session):
    before = deepcopy(Entities(session).list("system_definition")[0])
    plan = build_distributed_plan(session)
    apply_plan(session, plan)
    session.commit()
    definition = Entities(session).list("system_definition")[0]
    assert definition["status"] == "draft"
    assert [r["id"] for r in before["roles"]] == [r["id"] for r in definition["roles"]]
    assert all(r["quantity_basis"]["status"] == "draft" for r in definition["roles"])
    assert all(r["quantity_basis"]["factor"] is None for r in definition["roles"])
    rules = Entities(session).list("knowledge")
    needs = [r for r in rules if r["kind"] == "accessory"]
    assert len(needs) == 2 and all(r["status"] == "confirmed" for r in needs)
    assert all(not r["target_variant_ids"] and r["factor"] is None for r in needs)
    text_rule = next(r for r in rules if r["kind"] == "suitability")
    assert text_rule["role_id"] == next(
        r["id"] for r in definition["roles"] if r["name"] == "客户端软件"
    )
    assert text_rule["status"] == "draft"
    assert apply_plan(session, build_distributed_plan(session)) == []
    assert Entities(session).list("knowledge_package")[0]["status"] == "draft"


def test_later_maintainer_changes_and_history_survive_replay(session):
    apply_plan(session, build_distributed_plan(session))
    session.commit()
    entities = Entities(session)
    definition = entities.list("system_definition")[0]
    payload = {k: deepcopy(v) for k, v in definition.items() if k in SystemDefinition.model_fields}
    payload["roles"][0]["quantity_basis"].update(input_key="maintainer_custom", evidence="后续核对")
    updated = Definitions(session).save_definition(
        SystemDefinition.model_validate(payload),
        entity_id=definition["id"],
        expected_revision=definition["revision"],
    )
    session.commit()
    plan = build_distributed_plan(session)
    assert plan["changes"][0]["changed"] is False
    apply_plan(session, plan)
    assert entities.get(definition["id"]).revision == updated["revision"]
    assert MARKER not in entities.history(definition["id"])[-1]["evidence"]


def test_multiroom_verification_selects_distributed_uuid_roles(session):
    from verification.multiroom_stdio import configuration_operations

    definition = Entities(session).list("system_definition")[0]
    definitions = {DISTRIBUTED: definition}
    for name in ("EG 有线数字会议系统", "AI 智能纪要多会议室系统"):
        definitions[name] = dict(id=name, roles=[dict(id="software", name="软件")])
    operation = configuration_operations({}, [], definitions)[0]
    paper = next(s for s in operation["systems"] if s["system"]["id"] == "paper")
    assert len(paper["roles"]) == 12
    assert {r["role_id"] for r in paper["roles"]} == {r["id"] for r in definition["roles"]}
    assert "会议信息发布" in paper["system"]["features"]
