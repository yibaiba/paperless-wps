"""Isolated fixtures exercise source-backed needs and real ZEN capacity checks."""

from copy import deepcopy
from uuid import uuid4

import pytest
import zen
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Revision, SourceLink
from presales.configuration.projects.repository import ProjectConfigurations
from presales.configuration.projects.schemas import Configuration
from presales.rules.engine import ZenQuantityEngine
from presales.rules.repository import RuleConflict
from presales.storage import Base, CatalogImport, ProductRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .distributed_accessories import build_accessory_plan
from .distributed_accessory_facts import (
    FACTS,
    LIFT_QUOTE,
    MARKER,
    MODELS,
    STANDALONE_QUOTE,
)
from .maintenance import apply_plan
from .specs import DISTRIBUTED

AUTHOR = dict(actor="隔离配套测试", evidence="仅软件验证，数量和布置为测试输入")
ROLES = {
    21: "服务端软件",
    42: "升降/翻转显示设备",
    58: "数字会议主机",
    59: "主席话筒模块",
    60: "代表话筒模块",
}


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
            id="test",
            filename="synthetic.xlsx",
            digest="test",
            sheets=[DISTRIBUTED],
            record_count=len(MODELS),
            issue_count=0,
        )
    )
    session.flush()
    variants = {}
    for row, model in MODELS.items():
        product = entities.save("product", ProductInput(name=model, model=model, **AUTHOR))
        variant = entities.save(
            "variant",
            VariantInput(name=model, product_id=product["id"], status="confirmed", **AUTHOR),
        )
        variants[row] = variant["id"]
        session.add(
            ProductRecord(
                id=str(row),
                import_id="test",
                name=model,
                model=model,
                sheet=DISTRIBUTED,
                payload=dict(
                    sheet=DISTRIBUTED,
                    row=row,
                    prices={},
                    specification="\n".join(f.needle for f in FACTS.get(row, [])),
                    note=LIFT_QUOTE if 42 <= row <= 49 else STANDALONE_QUOTE,
                ),
            )
        )
        session.flush()
        session.add(SourceLink(source_id=str(row), variant_id=variant["id"], **AUTHOR))
    definition = Definitions(session).save_definition(
        SystemDefinition(
            name=DISTRIBUTED,
            roles=[dict(id=str(uuid4()), name=role, required=False) for role in ROLES.values()],
            **AUTHOR,
        )
    )
    rules = []
    for suffix, targets in (("module", [59, 60]), ("host", [58])):
        rules.append(
            entities.save(
                "knowledge",
                KnowledgeInput(
                    schema_version=2,
                    name="隔离配套",
                    kind="accessory",
                    status="draft",
                    selector=dict(variant_ids=[variants[row] for row in range(42, 50)]),
                    target_variant_ids=[variants[row] for row in targets],
                    need_key="distributed-paperless.microphone-" + suffix,
                    need_name=suffix,
                    **AUTHOR,
                ),
            )
        )
    Definitions(session).save_package(
        KnowledgePackage(
            name="隔离资料包",
            branch="测试",
            system_definition_id=definition["id"],
            definition_revision=1,
            members=[dict(id=r["id"], revision=1) for r in rules],
            **AUTHOR,
        )
    )
    session.commit()


def test_exact_needs_keep_quantity_unknown_and_history_immutable(session):
    history = {r.id: deepcopy(r.payload) for r in session.scalars(select(Revision))}
    definition = deepcopy(Entities(session).list("system_definition")[0])
    plan = build_accessory_plan(session)
    assert sum(c["changed"] for c in plan["changes"]) == 8
    apply_plan(session, plan)
    session.commit()
    assert apply_plan(session, build_accessory_plan(session)) == []
    assert Entities(session).list("system_definition")[0] == definition
    assert Entities(session).list("knowledge_package")[0]["status"] == "draft"
    rules = Entities(session).list("knowledge")
    assert len(rules) == 5
    assert all(r["status"] == "confirmed" and r["factor"] is None for r in rules)
    assert all(r["quantity_review"] == "unreviewed" and r["evidence_refs"] for r in rules)
    assert all(
        session.get(Revision, identity).payload == value for identity, value in history.items()
    )


def test_evidence_change_and_existing_quantity_prevent_automatic_rewrite(session):
    rule = Entities(session).list("knowledge")[0]
    entity = Entities(session).get(rule["id"])
    entity.payload = dict(entity.payload, mode="per_unit", factor="1")
    with pytest.raises(ValueError, match="已有不同范围或数量"):
        build_accessory_plan(session)
    session.rollback()
    plan = build_accessory_plan(session)
    source = session.get(ProductRecord, "42")
    source.payload = dict(source.payload, note="changed source")
    with pytest.raises(RuleConflict, match="维护依据已变化"):
        apply_plan(session, plan)


def configuration(session, *, rows, chair=12, delegate=100):
    definition = Entities(session).list("system_definition")[0]
    variants = {int(v["source_ids"][0]): v for v in CatalogService(session).variants()}
    requirements = []
    for row in rows:
        role = next(r for r in definition["roles"] if r["name"] == ROLES[row])
        resources = (
            []
            if row != 58
            else [
                dict(key=key, amount=str(amount), unit="个")
                for key, amount in (
                    ("microphone_chair_capacity", chair),
                    ("microphone_delegate_capacity", delegate),
                )
            ]
        )
        requirements.append(
            dict(
                id="r" + str(row),
                system_id="s",
                role_id=role["id"],
                role=role["name"],
                device_id="d" + str(row),
                resources=resources,
            )
        )
    return Configuration.model_validate(
        dict(
            calculation_version=3,
            decision_runtime="zen-v1",
            rooms=[dict(id="room", name="隔离会议室")],
            systems=[
                dict(
                    id="s",
                    name="隔离分布式",
                    kind=DISTRIBUTED,
                    definition_id=definition["id"],
                    room_id="room",
                )
            ],
            requirements=requirements,
            devices=[
                dict(
                    id="d" + str(row),
                    variant_id=variants[row]["id"],
                    source_id=str(row),
                    name=MODELS[row],
                    quantity="1",
                )
                for row in rows
            ],
            **AUTHOR,
        )
    )


@pytest.mark.parametrize(
    "chair,delegate,expected", [(12, 100, "pass"), (13, 100, "conflict"), (12, 101, "conflict")]
)
def test_actual_zen_checks_separate_host_capacities_without_invented_procurement(
    session, chair, delegate, expected
):
    apply_plan(session, build_accessory_plan(session))
    repository = ProjectConfigurations(session, ZenQuantityEngine(zen.ZenEngine()))
    checked = repository.check(configuration(session, rows=[58], chair=chair, delegate=delegate))
    limits = [c for c in checked["checks"] if c["kind"] == "capacity"]
    assert len(limits) == 2
    assert ("conflict" if any(c["status"] == "conflict" for c in limits) else "pass") == expected
    assert {c["resource"]: c["capacity"] for c in limits} == {
        "microphone_chair_capacity": "12",
        "microphone_delegate_capacity": "100",
    }
    need = next(s for s in checked["suggestions"] if s["rule"]["need_key"].endswith("host-lift"))
    assert need["status"] == "unknown" and need["required"] is None
    assert len(checked["configuration"]["devices"]) == 1


def test_lift_requires_both_categories_and_banner_never_becomes_a_credit(session):
    apply_plan(session, build_accessory_plan(session))
    repository = ProjectConfigurations(session, ZenQuantityEngine(zen.ZenEngine()))
    checked = repository.check(configuration(session, rows=[42, 21]))
    needs = {s["rule"]["need_key"]: s for s in checked["suggestions"]}
    assert set(needs) == {
        "distributed-paperless.microphone-module",
        "distributed-paperless.microphone-host",
    }
    assert all(s["required"] is None and s["status"] == "unknown" for s in needs.values())
    assert all(not s.get("included_offers") for s in needs.values())
    banner = next(v for v in CatalogService(session).variants() if "21" in v["source_ids"])
    item = banner["included_items"][0]
    assert item["quantity"] is None and item["variant_id"] is None and item["status"] == "draft"
    assert MARKER in banner["evidence"]
    assert len(checked["configuration"]["devices"]) == 2
