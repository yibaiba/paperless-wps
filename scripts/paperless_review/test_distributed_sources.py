"""Synthetic catalogue tests; never publish or fill real deployment quantities."""

from copy import deepcopy

import pytest
import zen
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.decisions.runtime import ZenDecisions
from presales.configuration.definitions.requirements import describe_requirements
from presales.configuration.knowledge.evaluator import context_for, environment_checks
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.knowledge.semantics import candidate_check_v3
from presales.configuration.models import SourceLink
from presales.rules.repository import RuleConflict
from presales.storage import ProductRecord

from .distributed_facts import FACTS, GENERIC_OS_GAP, MODELS, OS_ROWS, source_variant
from .distributed_sources import build_source_plan
from .maintenance import apply_plan
from .specs import DISTRIBUTED, THIRD_PARTY
from .test_distributed import AUTHOR
from .test_distributed import session as base_session  # noqa: F401


@pytest.fixture
def session(base_session):  # noqa: F811 - pytest injects the imported base fixture by name.
    entities = Entities(base_session)
    definition = entities.list("system_definition")[0]
    variants = CatalogService(base_session).variants()
    for row, facts in FACTS.items():
        variant = next(v for v in variants if str(row) in v["source_ids"])
        product = ProductInput(name=variant["name"], model=MODELS[row], **AUTHOR)
        entities.save("product", product, entity_id=variant["product_id"], expected_revision=1)
        source = base_session.get(ProductRecord, str(row))
        source.payload = dict(
            source.payload,
            sheet=DISTRIBUTED,
            specification="\n".join(f.needle for f in facts),
            note="无纸化系统搭建矩阵使用时请配置无缝混插矩阵",
        )
        if row not in OS_ROWS:
            continue
        role = next(r for r in definition["roles"] if r["name"] == OS_ROWS[row])
        entities.save(
            "knowledge",
            KnowledgeInput(
                name=OS_ROWS[row],
                kind="suitability",
                status="draft",
                system=DISTRIBUTED,
                system_definition_id=definition["id"],
                role=role["name"],
                role_id=role["id"],
                selector=dict(variant_ids=[variant["id"]]),
                **AUTHOR,
            ),
        )
    for row, model in ((15, "BYD5-W10"), (16, "BYD5-AL10")):
        product = entities.save("product", ProductInput(name=model, model=model, **AUTHOR))
        variant = entities.save(
            "variant", VariantInput(product_id=product["id"], name=model, **AUTHOR)
        )
        base_session.add(
            ProductRecord(
                id=str(row),
                import_id="i",
                name=model,
                model=model,
                sheet=THIRD_PARTY,
                payload=dict(
                    sheet=THIRD_PARTY, row=row, specification="HarmonyOS 4.2", note="", prices={}
                ),
            )
        )
        base_session.flush()
        base_session.add(SourceLink(source_id=str(row), variant_id=variant["id"], **AUTHOR))
    base_session.commit()
    return base_session


def test_only_evidenced_facts_and_environment_are_confirmed_and_replay_is_stable(session):
    original_definition = deepcopy(Entities(session).list("system_definition")[0])
    plan = build_source_plan(session)
    assert len([c for c in plan["changes"] if c["changed"]]) == 15
    apply_plan(session, plan)
    session.commit()
    entities = Entities(session)
    assert apply_plan(session, build_source_plan(session)) == []
    assert entities.list("system_definition")[0] == original_definition
    assert entities.list("knowledge_package")[0]["status"] == "draft"
    rules = entities.list("knowledge")
    tablets = [r for r in rules if r["role"] == "会议平板"]
    assert len(tablets) == 2 and all(r["status"] == "draft" for r in tablets)
    matrices = [r for r in rules if "matrix-" in r["need_key"]]
    assert len(matrices) == 2 and all(
        r["factor"] is None and not r["target_variant_ids"] for r in matrices
    )


def test_missing_quote_and_conflicting_manual_fact_fail_without_overwrite(session):
    source = session.get(ProductRecord, "65")
    original = dict(
        product_id="test",
        name="test",
        attributes=[dict(key="os", kind="enum", value=["Windows"])],
        **AUTHOR,
    )
    with pytest.raises(ValueError, match="已有属性"):
        source_variant(original, dict(source.payload, id=source.id))
    original["attributes"] = []
    with pytest.raises(ValueError, match="来源不包含"):
        source_variant(original, dict(source.payload, id=source.id, specification="其他产品"))
    plan = build_source_plan(session)
    source.payload = dict(source.payload, note="来源发生变化")
    with pytest.raises(RuleConflict, match="维护依据已变化"):
        apply_plan(session, plan)


def test_legacy_missing_description_and_unknown_os_are_repaired_from_exact_text(session):
    source = session.get(ProductRecord, "65")
    original = dict(
        product_id="test",
        name="test",
        attributes=[
            dict(key="os", kind="enum", value=None),
            dict(key="pending_questions", kind="text", value=GENERIC_OS_GAP + "\n显示配套未知"),
        ],
        **AUTHOR,
    )
    result = source_variant(original, dict(source.payload, id=source.id))
    attrs = {a["key"]: a for a in result["attributes"]}
    assert attrs["os"]["value"] == ["Android"]
    assert attrs["os_version"]["value"] == ["10"]
    assert attrs["pending_questions"]["value"] == "显示配套未知"
    assert "description" not in original


def test_real_zen_environment_and_conditional_matrix_keep_unknown_separate(session):
    apply_plan(session, build_source_plan(session))
    entities = Entities(session)
    definition = entities.list("system_definition")[0]
    rules = entities.list("knowledge")
    decisions = ZenDecisions(zen.ZenEngine())
    variant = next(v for v in CatalogService(session).variants() if "65" in v["source_ids"])
    variant["status"] = "confirmed"  # Isolated fixture only, not a public-data confirmation.
    rule = next(r for r in rules if r["role"] == OS_ROWS[65] and r["kind"] == "suitability")
    requirement = dict(
        system_definition_id=definition["id"],
        role_id=rule["role_id"],
        system=DISTRIBUTED,
        role=OS_ROWS[65],
        environment=[],
    )
    for os_name, version, status in (
        ("Android", "10", "pass"),
        ("Windows", "10", "conflict"),
        ("Android", "9", "conflict"),
        (None, None, "unknown"),
    ):
        requirement["environment"] = [
            dict(key=k, kind="enum", value=[v] if v else None, unit="")
            for k, v in (("os", os_name), ("os_version", version))
        ]
        assert (
            candidate_check_v3(
                variant, requirement=requirement, knowledge=rules, decisions=decisions
            )["status"]
            == status
        )
    matrix = next(r for r in rules if r["need_key"].endswith("matrix-input"))
    for choice, state in (("是", "pass"), ("否", "not_applicable"), (None, "unknown")):
        context = {
            "project.paperless_matrix_usage": dict(
                value=[choice] if choice else None, kind="enum", unit=""
            )
        }
        assert decisions.evaluate_rules([matrix], context)["evidence"][0]["result"] == state
    desc = describe_requirements(definition, rules=rules, features=[])
    field = next(
        f for r in desc["roles"] for f in r["inputs"] if f["key"] == "paperless_matrix_usage"
    )
    assert field["purpose"] == "project_input"
    request = dict(key=field["key"], kind="enum", unit="", value=["否"], purpose=field["purpose"])
    assert environment_checks(variant, [request], rules=[]) == []
    assert context_for(variant, [request])["project.paperless_matrix_usage"]["value"] == ["否"]
