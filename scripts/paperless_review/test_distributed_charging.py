"""Charging inputs run the real ZEN check, without inventing cart purchases."""

from copy import deepcopy

import pytest
import zen
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.requirements import RequirementDescription, read_description
from presales.configuration.definitions.schemas import SystemDefinition
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Revision, SourceLink
from presales.configuration.projects.candidates import candidate_results
from presales.configuration.projects.repository import ProjectConfigurations
from presales.configuration.projects.schemas import CandidateRequest, Configuration
from presales.rules.engine import ZenQuantityEngine
from presales.rules.repository import RuleConflict
from presales.storage import ProductRecord
from sqlalchemy import select

from .distributed_charging import INPUT_KEY, PROFILE_ID, ROLE, build_charging_plan
from .facts import CARTS, extracted, fact_rows
from .maintenance import apply_plan
from .reconciliation import MODELS
from .specs import DISTRIBUTED, THIRD_PARTY
from .test_distributed import AUTHOR
from .test_distributed import session as base_session  # noqa: F401


@pytest.fixture
def session(base_session):  # noqa: F811
    entities = Entities(base_session)
    variants = {}
    for row in CARTS:
        product = entities.save(
            "product", ProductInput(name=MODELS[row], model=MODELS[row], **AUTHOR)
        )
        source = dict(
            id=f"cart-{row}",
            row=row,
            sheet=THIRD_PARTY,
            prices={},
            note="",
            specification=fact_rows()[row][0].needle,
        )
        attribute, _ = extracted(source, fact_rows()[row][0])
        variant = entities.save(
            "variant",
            VariantInput(
                product_id=product["id"],
                name=MODELS[row],
                status="confirmed",
                attributes=[attribute],
                **AUTHOR,
            ),
        )
        variants[row] = variant["id"]
        base_session.add(
            ProductRecord(
                id=source["id"],
                import_id="i",
                name=MODELS[row],
                model=MODELS[row],
                sheet=THIRD_PARTY,
                payload={k: v for k, v in source.items() if k != "id"},
            )
        )
        base_session.flush()
        base_session.add(SourceLink(source_id=source["id"], variant_id=variant["id"], **AUTHOR))
    original = entities.list("system_definition")[0]
    data = SystemDefinition.model_validate(
        {k: v for k, v in original.items() if k in SystemDefinition.model_fields}
    ).model_dump(mode="json")
    data["roles"].append(dict(id="charging", name=ROLE, required=False, feature="集中充电"))
    Definitions(base_session).save_definition(
        SystemDefinition.model_validate(data),
        entity_id=original["id"],
        expected_revision=original["revision"],
    )
    entities.save(
        "knowledge",
        KnowledgeInput(
            name="已有充电候选",
            kind="suitability",
            status="draft",
            schema_version=2,
            system_definition_id=original["id"],
            system=DISTRIBUTED,
            role_id="charging",
            role=ROLE,
            selector=dict(variant_ids=[variants[33]]),
            **AUTHOR,
        ),
    )
    base_session.commit()
    return base_session


def config(session, *, row=33, demand="32", quantity="1"):
    definition = Entities(session).list("system_definition")[0]
    variant = next(
        v for v in CatalogService(session).variants() if f"cart-{row}" in v["source_ids"]
    )
    return Configuration.model_validate(
        dict(
            calculation_version=3,
            decision_runtime="zen-v1",
            rooms=[dict(id="room", name="隔离房间")],
            systems=[
                dict(
                    id="system",
                    name="隔离分布式",
                    kind=DISTRIBUTED,
                    definition_id=definition["id"],
                    room_id="room",
                    features=["集中充电"],
                    inputs=[]
                    if demand is None
                    else [dict(key=INPUT_KEY, kind="quantity", value=demand, unit="台")],
                )
            ],
            requirements=[
                dict(id="need", system_id="system", role_id="charging", role=ROLE, device_id="cart")
            ],
            devices=[
                dict(
                    id="cart",
                    name=MODELS[row],
                    variant_id=variant["id"],
                    source_id=f"cart-{row}",
                    quantity=quantity,
                )
            ],
            **AUTHOR,
        )
    )


def check(session, configuration):
    return ProjectConfigurations(session, ZenQuantityEngine(zen.ZenEngine())).check(configuration)


def capacity(result):
    return next(c for c in result["checks"] if c.get("resource") == "charging_capacity")


def test_atomic_idempotent_maintenance_pins_profile_preserves_history_and_drafts(session):
    old = {r.id: deepcopy(r.payload) for r in session.scalars(select(Revision))}
    plan = build_charging_plan(session)
    assert sum(c["changed"] for c in plan["changes"]) == 4
    apply_plan(session, plan)
    session.commit()
    assert apply_plan(session, build_charging_plan(session)) == []
    definition = Entities(session).list("system_definition")[0]
    assert definition["inspection_profiles"][0]["id"] == PROFILE_ID
    assert definition["status"] == "draft"
    assert Entities(session).list("knowledge_package")[0]["status"] == "draft"
    rule = next(r for r in Entities(session).list("knowledge") if r["role"] == ROLE)
    assert len(rule["selector"]["variant_ids"]) == 5 and rule["status"] == "draft"
    assert all(session.get(Revision, identity).payload == value for identity, value in old.items())


def test_input_available_before_selection_and_conditional_on_charging_feature(session):
    apply_plan(session, build_charging_plan(session))
    identity = Entities(session).list("system_definition")[0]["id"]
    for features, conditional in (([], True), (["集中充电"], False)):
        description = read_description(
            session, RequirementDescription(definition_id=identity, features=features)
        )
        field = next(f for f in description["shared_inputs"] if f["key"] == INPUT_KEY)
        assert (field["unit"], field["purpose"], field["conditional"]) == (
            "台",
            "project_input",
            conditional,
        )


def test_five_candidates_remain_unknown_without_compatibility_evidence(session):
    apply_plan(session, build_charging_plan(session))
    definition = Entities(session).list("system_definition")[0]
    candidates = candidate_results(
        CandidateRequest(
            calculation_version=3,
            system=DISTRIBUTED,
            role=ROLE,
            system_definition_id=definition["id"],
            role_id="charging",
        ),
        session=session,
    )
    assert len(candidates) == 5
    assert {item["status"] for item in candidates} == {"unknown"}


@pytest.mark.parametrize("row,limit", [(r, data[0]) for r, data in CARTS.items()])
def test_real_zen_uses_each_models_capacity(session, row, limit):
    apply_plan(session, build_charging_plan(session))
    passed = check(session, config(session, row=row, demand=str(limit)))
    exceeded = check(session, config(session, row=row, demand=str(limit + 1)))
    assert capacity(passed)["status"] == "pass"
    assert capacity(exceeded)["status"] == "conflict"
    assert capacity(passed)["capacity"] == str(limit)
    assert capacity(passed)["evidence"][0]["id"] == PROFILE_ID
    assert passed["configuration"]["requirements"][0]["resources"] == []
    assert len(passed["configuration"]["devices"]) == 1
    assert any(c["kind"] == "compatibility" and c["status"] == "unknown" for c in passed["checks"])


def test_quantity_changes_missing_zero_and_units_keep_distinct_meanings(session):
    apply_plan(session, build_charging_plan(session))
    for demand, quantity, expected, available in (
        ("32", "1", "pass", "36"),
        ("48", "1", "conflict", "36"),
        ("48", "2", "pass", "72"),
        ("0", "1", "pass", "36"),
    ):
        result = check(session, config(session, demand=demand, quantity=quantity))
        assert (capacity(result)["status"], capacity(result)["capacity"]) == (expected, available)
    missing = check(session, config(session, demand=None))
    assert not any(c.get("resource") == "charging_capacity" for c in missing["checks"])
    assert any(
        c.get("input_key") == INPUT_KEY and c["status"] == "unknown" for c in missing["checks"]
    )
    data = config(session).model_dump(mode="json")
    data["systems"][0]["inputs"][0].update(kind="number", unit="")
    wrong = check(session, Configuration.model_validate(data))
    assert any(c.get("input_key") == INPUT_KEY and "单位" in c["message"] for c in wrong["checks"])


def test_source_and_variant_changes_reject_stale_preview(session):
    plan = build_charging_plan(session)
    source = session.get(ProductRecord, "cart-33")
    source.payload = dict(source.payload, specification="changed")
    with pytest.raises(RuleConflict, match="依据已变化"):
        apply_plan(session, plan)
    session.rollback()
    variant = next(v for v in CatalogService(session).variants() if "cart-33" in v["source_ids"])
    entity = Entities(session).get(variant["id"])
    entity.payload = dict(entity.payload, attributes=[])
    with pytest.raises(RuleConflict, match="内容过期"):
        apply_plan(session, plan)


def test_old_project_snapshot_does_not_adopt_new_profile(session):
    previous = check(session, config(session))["configuration"]
    assert not any(
        c.get("resource") == "charging_capacity"
        for c in check(session, Configuration.model_validate(previous))["checks"]
    )
    apply_plan(session, build_charging_plan(session))
    unchanged = check(session, Configuration.model_validate(previous))
    assert not any(c.get("resource") == "charging_capacity" for c in unchanged["checks"])
    assert any(v["kind"] == "system_definition" for v in unchanged["version_changes"])
