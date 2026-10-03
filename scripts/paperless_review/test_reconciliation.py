"""Isolated validation of source facts, version preservation, and real ZEN quantities."""

from copy import deepcopy

import pytest
import zen
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Entity
from presales.configuration.projects.calculation.demands import quantity_missing
from presales.configuration.projects.planning.quantities import role_quantity
from presales.rules.calculation import digest
from presales.rules.engine import ZenQuantityEngine
from presales.rules.repository import RuleConflict
from presales.storage import Base, CatalogImport, ProductRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .facts import TABLETS, Fact, extracted
from .maintenance import apply_plan, proposal
from .reconciliation import (
    current_records,
    definition_payload,
    evidence_source_ids,
    package_changes,
    variant_payload,
)
from .reconciliation_rules import corrected_rule
from .specs import DISTRIBUTED

AUTHOR = dict(actor="隔离测试", evidence="合成来源，不是业务结论")


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        entities = Entities(session)
        product = entities.save("product", ProductInput(name="测试平板", model="TEST", **AUTHOR))
        variant = entities.save(
            "variant", VariantInput(product_id=product["id"], name="测试配置", **AUTHOR)
        )
        entities.save(
            "knowledge",
            KnowledgeInput(
                name="测试关系",
                kind="suitability",
                system="隔离",
                role="平板",
                status="confirmed",
                selector=dict(variant_ids=[variant["id"]]),
                **AUTHOR,
            ),
        )
        session.add(
            CatalogImport(
                id="import",
                filename="synthetic.xlsx",
                digest="test-only",
                sheets=["测试"],
                record_count=1,
                issue_count=0,
            )
        )
        session.flush()
        session.add(
            ProductRecord(
                id="source",
                import_id="import",
                model="TEST",
                name="测试",
                sheet="测试",
                payload=dict(specification="8GB", prices={"测试价格": "123"}),
            )
        )
        session.commit()
        yield session
    engine.dispose()


def variant_plan(session):
    variant = session.scalar(select(Entity).where(Entity.kind == "variant"))
    current = {
        variant.id: dict(
            kind="variant", revision=variant.revision, payload=deepcopy(variant.payload)
        )
    }
    payload = dict(
        variant.payload,
        attributes=[dict(key="memory", kind="quantity", value="8", unit="GB")],
    )
    change = proposal(current, kind="variant", identity=variant.id, payload=payload)
    return dict(
        changes=[change],
        fingerprint=digest([change]),
        source_guards={"source": digest(session.get(ProductRecord, "source").payload)},
    )


def test_catalogue_service_keeps_review_impact_and_retries_without_new_revisions(
    session,
):
    before_source = deepcopy(session.get(ProductRecord, "source").payload)
    plan = variant_plan(session)
    result = apply_plan(session, plan)
    session.commit()
    assert len(result) == 1 and result[0]["revision"] == 2
    assert result[0]["review_requirements"]
    assert len(Entities(session).list("catalog_impact")) == 1
    assert apply_plan(session, plan) == []
    assert apply_plan(session, variant_plan(session)) == []
    assert len(Entities(session).history(result[0]["id"])) == 2
    assert session.get(ProductRecord, "source").payload == before_source


def test_source_change_rejects_before_any_variant_write(session):
    plan = variant_plan(session)
    record = session.get(ProductRecord, "source")
    record.payload = dict(record.payload, specification="16GB")
    session.commit()
    with pytest.raises(RuleConflict, match="维护依据已变化"):
        apply_plan(session, plan)
    assert session.get(Entity, plan["changes"][0]["id"]).revision == 1
    assert Entities(session).list("catalog_impact") == []


def test_package_defaults_do_not_break_retry_or_add_revisions(session):
    definitions = Definitions(session)
    definition = definitions.save_definition(SystemDefinition(name="测试系统", **AUTHOR))
    package = definitions.save_package(
        KnowledgePackage(
            name="测试资料包",
            system_definition_id=definition["id"],
            definition_revision=1,
            branch="测试分支",
            **AUTHOR,
        )
    )
    # Old persisted inputs precede the addition of recommendation defaults.
    record = session.get(Entity, package["id"])
    record.payload = {k: v for k, v in record.payload.items() if k != "recommendations"}
    session.commit()
    current = current_records(session)
    change = proposal(
        current,
        kind="system_definition",
        identity=definition["id"],
        payload=SystemDefinition(
            name="测试系统", actor=AUTHOR["actor"], evidence="测试新增依据"
        ).model_dump(mode="json"),
    )
    changes = [change, *package_changes(current, [change])]
    plan = dict(changes=changes, fingerprint=digest(changes))
    assert len(apply_plan(session, plan)) == 2
    session.commit()
    assert apply_plan(session, plan) == []
    assert len(Entities(session).history(package["id"])) == 2
    assert session.get(Entity, package["id"]).payload["recommendations"] == []


def test_source_guards_include_nested_role_and_fulfillment_evidence():
    reference = dict(source_id="nested-source", quote="测试原文", locator="测试!A1")
    payload = dict(roles=[dict(quantity_basis=dict(evidence_refs=[reference]))])
    assert evidence_source_ids(payload) == {"nested-source"}


def test_concurrent_maintainer_change_is_not_overwritten(session):
    plan = variant_plan(session)
    record = session.get(Entity, plan["changes"][0]["id"])
    Entities(session).save(
        "variant",
        dict(record.payload, evidence="维护者新依据"),
        entity_id=record.id,
        expected_revision=1,
    )
    session.commit()
    with pytest.raises(RuleConflict, match="预览版本过期"):
        apply_plan(session, plan)
    assert session.get(Entity, record.id).payload["evidence"] == "维护者新依据"


def test_source_fact_keeps_unknown_version_and_original_unicode_evidence():
    source = dict(
        id="source",
        sheet="测试",
        row=16,
        specification="操作系统：HarmonyOS 4.2 / 4.3‌（预装）",
    )
    fact = next(f for f in TABLETS[16] if f.key == "os_version")
    attribute, reference = extracted(source, fact)
    assert attribute["value"] is None
    assert reference["quote"] == source["specification"]
    with pytest.raises(ValueError, match="不包含预期事实"):
        extracted(dict(source, specification="Windows"), fact)


def test_conflicting_existing_attribute_is_not_replaced(session):
    variant = session.scalar(select(Entity).where(Entity.kind == "variant"))
    before = dict(
        variant.payload,
        attributes=[dict(key="memory", kind="quantity", value="16", unit="GB")],
    )
    source = dict(id="source", sheet="测试", row=15, specification="8GB")
    with pytest.raises(ValueError, match="未覆盖"):
        variant_payload(
            dict(payload=before),
            source=source,
            facts=[Fact("memory", "quantity", "8", "GB", "8GB")],
        )


def test_ap_authorization_does_not_become_unconditional_extra_purchase():
    class Sources:
        def evidence(self, sheet, row, *, quote):
            return dict(source_id=f"test-{row}", locator=sheet, quote=quote)

    old = KnowledgeInput(
        name="测试旧授权",
        kind="accessory",
        selector=dict(variant_ids=["test-ap"]),
        target_variant_ids=["test-license"],
        need_key="third-party.huawei-ap-license",
        status="confirmed",
        **AUTHOR,
    ).model_dump(mode="json")
    result = corrected_rule(old, Sources())
    assert result["status"] == "draft" and result["mode"] is None
    assert result["factor"] is None and quantity_missing(result)
    assert len(result["evidence_refs"]) == 3
    assert old["status"] == "confirmed"  # No mutation of the previous revision.


def test_role_types_and_source_confirmed_quantity_use_real_zen():
    definition = dict(
        name=DISTRIBUTED,
        status="draft",
        roles=[
            dict(id="software", name="服务端软件", required=False),
            dict(id="rooms", name="会议室授权", required=False),
            dict(id="terminal", name="会议平板", required=False),
        ],
        **AUTHOR,
    )
    rule = dict(
        need_key="distributed-paperless.room-license",
        status="confirmed",
        quantity_review="confirmed",
        calculation_scope="project",
        quantity_key="room_count",
        quantity_unit="",
        mode="per_unit",
        factor="1",
        quantity_evidence="隔离资料：按会议室数量收取",
        evidence_refs=[],
    )
    result = definition_payload(definition, [rule])
    roles = {r["id"]: r for r in result["roles"]}
    assert roles["software"]["output_kind"] == "software"
    assert roles["rooms"]["output_kind"] == "license"
    assert roles["terminal"]["quantity_basis"] is None
    assert roles["rooms"]["fulfilled_by"]["role_id"] == "software"
    assert result["status"] == "draft" and not any(r["required"] for r in result["roles"])
    engine = ZenQuantityEngine(zen.ZenEngine())
    system = dict(id="test", inputs=[])
    for rooms in (1, 2, 3):
        configuration = dict(project_inputs=[dict(key="room_count", value=str(rooms), unit="")])
        quantity, gap, evidence = role_quantity(
            roles["rooms"], system, configuration=configuration, engine=engine
        )
        assert quantity == rooms and gap is None
        assert "ZEN" in evidence["calculation"]["engine"]
    quantity, gap, _ = role_quantity(roles["rooms"], system, configuration={}, engine=engine)
    assert quantity is None and gap["code"] == "quantity_input_missing"
