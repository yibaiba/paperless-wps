"""Isolated source fixtures: never install test products or approvals in the business DB."""

from copy import deepcopy

import pytest
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.common import Entities
from presales.configuration.definitions.inspection_schemas import InspectionProfile
from presales.configuration.definitions.schemas import SystemDefinition
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput, with_completion
from presales.configuration.models import Entity, Revision, SourceLink
from presales.configuration.projects.calculation.demands import quantity_missing
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict
from presales.storage import Base, CatalogImport, ProductRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .content import ReviewSources, reviewed_accessory, reviewed_suitability
from .maintenance import apply_plan
from .planning import build_plan
from .specs import DISTRIBUTED, SAFE, THIRD_PARTY

AUTHOR = dict(actor="隔离测试", evidence="合成来源，仅验证维护流程，不是业务结论")
ROWS = {
    DISTRIBUTED: {
        7: "每个签到终端需发放一个授权",
        22: "按会议室数量收取",
        24: "测试输入参数",
        25: "测试输出参数",
        33: "测试推荐平板与交换机",
    },
    SAFE: {9: "测试服务端", 10: "测试客户端"},
    THIRD_PARTY: {12: "测试移动部署电脑", 33: "测试36台容量"},
}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        seed_sources(value)
        yield value
    engine.dispose()


def seed_sources(session):
    session.add(
        CatalogImport(
            id="test-import",
            filename="synthetic.xlsx",
            digest="test-only",
            sheets=list(ROWS),
            record_count=9,
            issue_count=0,
        )
    )
    session.flush()
    entities = Entities(session)
    product = entities.save("product", ProductInput(name="测试产品", model="TEST", **AUTHOR))
    for sheet, rows in ROWS.items():
        for row, note in rows.items():
            identity = f"{sheet}-{row}"
            variant = entities.save(
                "variant",
                VariantInput(
                    product_id=product["id"],
                    name=identity,
                    status="confirmed",
                    **AUTHOR,
                ),
            )
            session.add(
                ProductRecord(
                    id=identity,
                    import_id="test-import",
                    model="TEST",
                    name="测试来源",
                    sheet=sheet,
                    payload=dict(row=row, specification=note, note=note, prices={}),
                )
            )
            session.flush()
            session.add(
                SourceLink(
                    source_id=identity,
                    variant_id=variant["id"],
                    actor=AUTHOR["actor"],
                    evidence=AUTHOR["evidence"],
                )
            )
    session.commit()


def old_rule(session, *, key="distributed-paperless.tablet-hardware"):
    variant = session.scalar(
        select(SourceLink).where(SourceLink.source_id == f"{DISTRIBUTED}-33")
    ).variant_id
    rule = KnowledgeInput(
        name="测试旧公式",
        kind="accessory",
        status="confirmed",
        selector={"variant_ids": [variant]},
        target_variant_ids=[variant],
        need_key=key,
        mode="per_unit",
        factor=1,
        **AUTHOR,
    )
    return Entities(session).save("knowledge", rule)


def test_full_batch_retry_rebuild_and_fixed_history(session):
    old = old_rule(session)
    session.commit()
    plan = build_plan(session)
    result = apply_plan(session, plan)
    session.commit()
    assert len(result) == 13  # two definitions, eight additions, two packages, one correction
    assert apply_plan(session, plan) == []
    regenerated = build_plan(session)
    assert not any(item["changed"] for item in regenerated["changes"])
    assert apply_plan(session, regenerated) == []
    history = Entities(session).history(old["id"])
    assert [r["revision"] for r in history] == [2, 1]
    assert history[1]["factor"] == "1" and history[0]["factor"] is None
    packages = Entities(session).list("knowledge_package")
    assert len(packages) == 2 and all(p["status"] == "draft" for p in packages)
    assert any(m == {"id": old["id"], "revision": 2} for p in packages for m in p["members"])
    assert all(c["accessories"] == "needs_review" for p in packages for c in p["coverage"])


def test_explicit_quantity_and_unknown_quantity_are_distinct(session):
    old_rule(session)
    old_rule(session, key="distributed-paperless.room-license")
    session.commit()
    apply_plan(session, build_plan(session))
    rules = Entities(session).list("knowledge")
    tablet = next(r for r in rules if r.get("need_key") == "distributed-paperless.tablet-hardware")
    licence = next(r for r in rules if r.get("need_key") == "distributed-paperless.room-license")
    assert with_completion(tablet)["completion"] == "incomplete"
    assert quantity_missing(tablet)
    assert licence["quantity_review"] == "confirmed" and not quantity_missing(licence)
    switch = next(r for r in rules if r.get("need_key") == "distributed-paperless.network-switch")
    assert switch["status"] == "confirmed" and switch["factor"] is None
    assert quantity_missing(switch)  # confirmed need does not imply an applicable formula


def test_stale_batch_does_not_create_definitions(session):
    old = old_rule(session)
    session.commit()
    plan = build_plan(session)
    payload = {k: v for k, v in old.items() if k not in {"id", "revision", "updated_at"}}
    Entities(session).save(
        "knowledge",
        {**payload, "evidence": "维护者新证据"},
        entity_id=old["id"],
        expected_revision=1,
    )
    session.commit()
    with pytest.raises(RuleConflict):
        apply_plan(session, plan)
    assert Entities(session).list("system_definition") == []


def test_bad_reference_rolls_back_entire_batch(session):
    plan = build_plan(session)
    bad = next(c for c in plan["changes"] if c["kind"] == "knowledge")
    bad["payload"]["selector"]["variant_ids"] = ["missing-variant"]
    plan["fingerprint"] = digest(plan["changes"])
    with pytest.raises(ValueError):
        apply_plan(session, plan)
    session.rollback()
    assert Entities(session).list("system_definition") == []
    assert Entities(session).list("knowledge") == []


def test_changed_preview_fails_before_writes(session):
    plan = build_plan(session)
    plan["changes"][0]["payload"]["name"] = "修改过的预览"
    with pytest.raises(ValueError, match="预览内容"):
        apply_plan(session, plan)
    assert Entities(session).list("system_definition") == []


def test_only_adjacent_pairing_is_demoted_and_old_formula_untouched():
    payload = KnowledgeInput(
        name="测试软件",
        kind="accessory",
        status="confirmed",
        selector={"variant_ids": ["a"]},
        target_variant_ids=["b"],
        need_key="safe-paperless.cast-software",
        factor=1,
        **AUTHOR,
    ).model_dump(mode="json")
    before = deepcopy(payload)
    result = reviewed_accessory(payload, ReviewSources([]))
    assert payload == before
    assert result["status"] == "draft" and result["factor"] is None


def test_evidence_must_exist_in_the_expected_source():
    sources = ReviewSources(
        [
            dict(
                id="a",
                source_details=[
                    dict(
                        id="s",
                        sheet=THIRD_PARTY,
                        row=12,
                        note="无部署声明",
                        specification="测试",
                    )
                ],
            )
        ]
    )
    with pytest.raises(ValueError, match="预期原文"):
        sources.evidence(THIRD_PARTY, 12, quote="可作为移动式部署的服务器")


def test_preview_rollback_retains_original_revision(session):
    original = old_rule(session)
    session.commit()
    apply_plan(session, build_plan(session))
    session.rollback()
    assert Entities(session).get(original["id"]).revision == 1
    assert len(Entities(session).history(original["id"])) == 1
    assert (
        session.scalar(select(Revision).where(Revision.entity_id == original["id"])).revision == 1
    )
    assert session.scalar(select(Entity).where(Entity.kind == "knowledge_package")) is None


def test_client_case_evidence_keeps_status_and_does_not_duplicate_references():
    sources = ReviewSources(
        [
            dict(
                id="test-bundle",
                source_details=[
                    dict(
                        id="test-source",
                        sheet="红盾无纸化会议系统华为版本",
                        row=12,
                        note="内置RS-MSC100C红盾无纸化软件",
                    )
                ],
            )
        ]
    )
    original = KnowledgeInput(
        name="测试客户端",
        kind="suitability",
        status="draft",
        selector={"variant_ids": ["test-client"]},
        system=SAFE,
        role="客户端软件",
        **AUTHOR,
    ).model_dump(mode="json")
    reviewed = reviewed_suitability(original, sources)
    repeated = reviewed_suitability(reviewed, sources)
    assert repeated == reviewed and repeated["status"] == "draft"
    assert len(repeated["evidence_refs"]) == 1
    assert "型号仍保留PB30S" in repeated["evidence"]
    assert "不能据此抵扣20S/30S软件" in repeated["evidence"]


def test_rebuild_preserves_later_role_edits_and_fixed_inspection_snapshot(session):
    apply_plan(session, build_plan(session))
    session.commit()
    entities = Entities(session)
    profile = entities.save("inspection_profile", InspectionProfile(name="测试用途", **AUTHOR))
    definition = next(d for d in entities.list("system_definition") if d["name"] == DISTRIBUTED)
    payload = {
        k: v
        for k, v in definition.items()
        if k not in {"id", "revision", "updated_at", "inspection_profiles"}
    }
    payload["roles"][0].update(required=True, inspection_profile=dict(id=profile["id"], revision=1))
    payload.update(evidence="维护者后续核对依据", legacy_names=["后续别名"])
    updated = Definitions(session).save_definition(
        SystemDefinition.model_validate(payload),
        entity_id=definition["id"],
        expected_revision=definition["revision"],
    )
    session.commit()
    plan = build_plan(session)
    item = next(c for c in plan["changes"] if c["id"] == definition["id"])
    assert not item["changed"]
    assert item["payload"] == payload
    apply_plan(session, plan)
    session.commit()
    assert entities.get(definition["id"]).revision == updated["revision"]
    assert entities.get(definition["id"]).payload["inspection_profiles"][0]["id"] == profile["id"]
    assert apply_plan(session, plan) == []
