"""Synthetic rows isolate maintenance correctness from actual business conclusions."""

from copy import deepcopy

import pytest
from presales.configuration.common import Entities, view
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import SourceLink
from presales.configuration.projects.calculation.demands import quantity_missing
from presales.rules.repository import RuleConflict
from presales.storage import Base, CatalogImport, ProductRecord
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .booking_scope import SYSTEM, build_scope_plan
from .booking_specs import ACCESSORIES, DEFINITION, MAPPINGS, MODELS, PACKAGE, SHEET
from .maintenance import apply_plan

AUTHOR = dict(actor="隔离测试", evidence="合成维护测试资料，不是实际产品结论")


@pytest.fixture
def case():
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
            filename="synthetic.xlsx",
            digest="test",
            sheets=[],
            record_count=len(MODELS),
            issue_count=0,
        )
    )
    product = entities.save("product", dict(name="测试", model="TEST", **AUTHOR))
    quotes = {s.row: s.quote for s in MAPPINGS}
    quotes.update({s.target_row: s.quote for s in ACCESSORIES if s.quote})
    for row, model in MODELS.items():
        entities.save(
            "variant",
            dict(product_id=product["id"], name="测试配置", **AUTHOR),
            create_id=f"v{row}",
        )
        session.add(
            ProductRecord(
                id=f"s{row}",
                import_id="i",
                name="测试来源",
                model=model,
                sheet=SHEET,
                payload=dict(
                    row=row,
                    specification=quotes.get(row, "测试原文"),
                    sources=dict(specification=f"F{row}"),
                ),
            )
        )
        session.flush()
        session.add(SourceLink(source_id=f"s{row}", variant_id=f"v{row}", **AUTHOR))
    definitions = Definitions(session)
    definitions.save_definition(
        SystemDefinition(
            name=SYSTEM,
            roles=[
                dict(id="server-software", name="服务端软件", required=False),
                dict(id="server", name="服务器", required=False),
                dict(id="terminal", name="终端", required=False),
                dict(id="license", name="授权", required=False),
            ],
            **AUTHOR,
        ),
        create_id=DEFINITION,
    )
    for spec in (*MAPPINGS, *ACCESSORIES):
        payload = seed_rule(spec)
        entities.save("knowledge", payload, create_id=spec.identity)
        if spec.revision == 2:
            entities.save("knowledge", payload, entity_id=spec.identity, expected_revision=1)
    package = KnowledgePackage(
        name="隔离预约资料包",
        branch="测试",
        system_definition_id=DEFINITION,
        definition_revision=1,
        members=[dict(id=s.identity, revision=s.revision) for s in ACCESSORIES if not s.quote],
        **AUTHOR,
    )
    definitions.save_package(package, create_id=PACKAGE)
    definitions.save_package(package, entity_id=PACKAGE, expected_revision=1)
    session.commit()


def seed_rule(spec):
    if spec in MAPPINGS:
        return KnowledgeInput(
            kind="suitability",
            name="测试角色",
            system="会议预约",
            role=spec.old_role,
            status="draft" if spec.row == 23 else "confirmed",
            selector=dict(variant_ids=[f"v{spec.row}"]),
            conditions=[dict(field="project.os", operator="eq", value="Linux")],
            **AUTHOR,
        )
    return KnowledgeInput(
        kind="accessory",
        name="测试配套",
        status="confirmed",
        selector=dict(variant_ids=[f"v{r}" for r in spec.source_rows]),
        target_variant_ids=[f"v{spec.target_row}"],
        need_key="booking." + spec.key,
        accessory_type="optional" if spec.key.startswith("integration.") else "required",
        calculation_scope="system",
        mode="per_unit" if spec.quote else "per_group",
        factor=1,
        **AUTHOR,
    )


def test_scope_quantity_history_and_replay(case):
    entities = Entities(case)
    old_package = deepcopy(view(entities.get(PACKAGE)))
    plan = build_scope_plan(case)
    assert len(apply_plan(case, plan)) == 17
    case.commit()
    current = view(entities.get(PACKAGE))
    assert current["status"] == "draft" and current["definition_revision"] == 2
    assert len(current["members"]) == 14  # synthetic package omits the software suitability row
    for spec in MAPPINGS:
        rule = entities.get(spec.identity).payload
        assert rule["role_id"] == spec.role_id and rule["system_definition_id"] == DEFINITION
        assert rule["status"] == ("draft" if spec.row == 23 else "confirmed")
        assert rule["conditions"] == entities.history(spec.identity)[-1]["conditions"]
    for spec in ACCESSORIES:
        rule = entities.get(spec.identity).payload
        assert bool(quantity_missing(rule)) == (not bool(spec.quote))
        if not spec.quote:
            assert rule["factor"] is None and rule["mode"] is None
        if spec.key.startswith("integration."):
            assert rule["accessory_type"] == "optional" and rule["status"] == "confirmed"
    assert entities.history(PACKAGE)[-1]["members"] == old_package["members"]
    assert apply_plan(case, plan) == [] and apply_plan(case, build_scope_plan(case)) == []


@pytest.mark.parametrize("failure", ["source", "scope", "quote", "revision", "published"])
def test_invalid_or_changed_evidence_never_partially_applies(case, failure):
    entities = Entities(case)
    plan = build_scope_plan(case)
    if failure in ("source", "quote"):
        record = case.get(ProductRecord, "s19")
        record.payload = dict(record.payload, specification="原文变更")
    elif failure == "scope":
        record = entities.get(ACCESSORIES[0].identity)
        record.payload = dict(record.payload, target_variant_ids=["v18"])
    else:
        record = entities.get(PACKAGE)
        record.revision += 1
        if failure == "published":
            record.payload = dict(record.payload, status="published")
    case.flush()
    with pytest.raises((ValueError, RuleConflict)):
        apply_plan(case, plan) if failure == "source" else build_scope_plan(case)
    assert entities.get(DEFINITION).revision == 1


def test_later_maintenance_is_preserved(case):
    apply_plan(case, build_scope_plan(case))
    case.commit()
    entities = Entities(case)
    record = entities.get(MAPPINGS[0].identity)
    entities.save(
        "knowledge",
        dict(record.payload, status="draft"),
        entity_id=record.id,
        expected_revision=record.revision,
    )
    before = deepcopy(entities.get(PACKAGE).payload)
    assert apply_plan(case, build_scope_plan(case)) == []
    assert entities.get(PACKAGE).payload == before
    assert entities.get(MAPPINGS[0].identity).payload["status"] == "draft"


def test_source_reassignment_between_preview_and_apply_is_rejected(case):
    plan = build_scope_plan(case)
    case.get(SourceLink, "s21").variant_id = "v22"
    case.flush()
    with pytest.raises(RuleConflict, match="来源配置归属已变化"):
        apply_plan(case, plan)
    assert Entities(case).get(DEFINITION).revision == 1
