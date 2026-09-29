from copy import deepcopy
from uuid import uuid4

import pytest

from presales.configuration.catalog.schemas import VariantInput
from presales.configuration.definitions.schemas import KnowledgePackage
from presales.rules.calculation import digest

from .conftest import knowledge, post
from .test_catalog_updates import batch_for, call, decision, edit
from .test_proposal_generation import published


def fields(record):
    return {key: value for key, value in record.items() if key in VariantInput.model_fields}


def revise(client, record, payload, path="knowledge"):
    response = client.put(
        f"/api/configuration/{path}/{record['id']}",
        json=dict(expected_revision=record["revision"], payload=payload),
    )
    assert response.status_code == 200, response.text
    return response.json()


def mixed_rules(client, catalog, config, *, scope="project", incomplete=False):
    definition, package = published(client, catalog, accessory=True)
    rule = next(
        r for r in client.get("/api/configuration/knowledge").json() if r["kind"] == "accessory"
    )
    payload = {k: v for k, v in rule.items() if k not in {"id", "revision", "updated_at"}}
    payload.update(calculation_scope=scope, allocation_mode="consumable", factor="1")
    if incomplete:
        payload.update(quantity_review="unreviewed", factor=None)
    old = revise(client, rule, payload)
    package_payload = {k: v for k, v in package.items() if k in KnowledgePackage.model_fields}
    package_payload["members"] = [
        dict(m, revision=old["revision"]) if m["id"] == rule["id"] else m
        for m in package["members"]
    ]
    revise(client, package, package_payload, "knowledge-packages")
    payload.update(factor=None if incomplete else "2")
    revise(client, old, payload)
    config.update(calculation_version=3)
    config["systems"] = [
        dict(
            id=i,
            room_id="room",
            name=i,
            kind=definition["name"],
            definition_id=definition["id"],
            knowledge_package_id=package["id"] if i == "pinned" else "",
        )
        for i in ["pinned", "latest"]
    ]
    config["devices"] = [dict(config["devices"][0], id=i) for i in ["d1", "d2"]]
    config["requirements"] = [
        dict(id=i, system_id=s, role="终端", role_id="terminal", device_id=d)
        for i, s, d in [("r1", "pinned", "d1"), ("r2", "latest", "d2")]
    ]
    return rule


def selected_demands(checked, rule):
    return sorted(
        (s for s in checked["suggestions"] if s["rule"]["id"] == rule["id"]),
        key=lambda s: s["rule"]["revision"],
    )


def apply_demand(client, catalog, checked, demand):
    return post(
        client,
        "/apply",
        dict(
            configuration=checked["configuration"],
            fingerprint=checked["fingerprint"],
            suggestion_id=demand["id"],
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity=demand["missing"],
        ),
    )


@pytest.mark.parametrize("scope", ["project", "room"])
def test_mixed_revisions_can_be_fulfilled_independently(client, catalog, config, scope):
    rule = mixed_rules(client, catalog, config, scope=scope)
    checked = post(client, "/check", dict(configuration=config))
    old, current = selected_demands(checked, rule)
    assert old["id"] != current["id"]
    assert [old["required"], current["required"]] == ["1", "2"]
    assert [old["consumer_requirement_ids"], current["consumer_requirement_ids"]] == [
        ["r1"],
        ["r2"],
    ]
    first = apply_demand(client, catalog, checked, old)
    assert [d["existing"] for d in selected_demands(first, rule)] == ["1", "0"]
    second = apply_demand(client, catalog, first, selected_demands(first, rule)[1])
    assert [d["missing"] for d in selected_demands(second, rule)] == ["0", "0"]
    assert len(second["configuration"]["devices"]) == 4
    again = apply_demand(client, catalog, second, current)
    assert len(again["configuration"]["devices"]) == 4
    # Removing the other scope must not orphan the remaining qualified allocation.
    reduced = deepcopy(second["configuration"])
    reduced["systems"] = reduced["systems"][:1]
    reduced["requirements"] = reduced["requirements"][:1]
    reduced["devices"] = [d for d in reduced["devices"] if d["id"] != "d2"]
    reduced["accessory_allocations"] = [
        a for a in reduced["accessory_allocations"] if a["demand_id"] == old["id"]
    ]
    reopened = post(client, "/check", dict(configuration=reduced))
    remaining = selected_demands(reopened, rule)
    assert len(remaining) == 1
    assert remaining[0]["id"] == old["id"] and remaining[0]["missing"] == "0"


def test_incomplete_mixed_demands_also_have_distinct_identities(client, catalog, config):
    rule = mixed_rules(client, catalog, config, incomplete=True)
    demands = selected_demands(post(client, "/check", dict(configuration=config)), rule)
    assert len(demands) == len({d["id"] for d in demands}) == 2
    assert all(d["status"] == "unknown" and d["required"] is None for d in demands)


def test_ambiguous_legacy_allocation_is_retained_but_never_double_credited(client, catalog, config):
    rule = mixed_rules(client, catalog, config)
    legacy_id = digest([rule["id"], "project", "project"])
    config["devices"].append(
        dict(
            id="stock",
            name="历史配套",
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity="1",
            kind="hardware",
            origin_suggestion=legacy_id,
        )
    )
    allocation = dict(
        id="legacy-allocation",
        demand_id=legacy_id,
        device_id="stock",
        quantity="1",
        evidence="历史分配",
    )
    config["accessory_allocations"] = [allocation]
    checked = post(client, "/check", dict(configuration=config))
    assert all(d["existing"] == "0" for d in selected_demands(checked, rule))
    assert checked["configuration"]["accessory_allocations"] == [allocation]
    assert any(
        c["kind"] == "accessory_allocation"
        and c["status"] == "unknown"
        and c["demand_id"] == legacy_id
        for c in checked["checks"]
    )


@pytest.mark.parametrize("review_field", ["omitted", "empty", "stale"])
def test_noop_correction_keeps_pending_reviews(client, catalog, review_field):
    original = catalog["variants"][0]
    rule = knowledge(client, original)
    value = fields(original)
    value["attributes"] = [
        dict(a, value="arm64") if a["key"] == "cpu_arch" else a for a in value["attributes"]
    ]
    changed = revise(client, original, value, "variants")
    assert changed["review_requirements"]
    value = fields(changed)
    value.pop("review_requirements")
    if review_field == "empty":
        value["review_requirements"] = []
    elif review_field == "stale":
        value["review_requirements"] = [dict(id=rule["id"], revision=0, name=rule["name"])]
    batch = edit(
        client, batch_for(client, changed), dict(decision(changed, variant=value), action="correct")
    )
    request = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", request)
    call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**request, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
    )
    candidates = post(
        client, "/candidates", dict(calculation_version=3, system="无纸化", role="服务端")
    )
    candidate = next(c for c in candidates if c["variant"]["id"] == original["id"])
    assert candidate["status"] == "unknown"
    assert candidate["variant"]["review_requirements"] == changed["review_requirements"]
    # A genuinely reviewed knowledge revision still resolves the pending check.
    payload = {k: v for k, v in rule.items() if k not in {"id", "revision", "updated_at"}}
    revise(client, rule, dict(payload, reviewed_variant_ids=[original["id"]]))
    candidates = post(
        client, "/candidates", dict(calculation_version=3, system="无纸化", role="服务端")
    )
    assert next(c for c in candidates if c["variant"]["id"] == original["id"])["status"] == "pass"


def test_unambiguous_historical_demand_identity_stays_unchanged():
    from presales.configuration.projects.calculation.demand_identity import DemandIdentities

    rule = dict(id="rule", revision=7, calculation_scope="project")
    data = dict(devices=[], accessory_allocations=[], included_allocations=[], accessory_choices=[])
    before = deepcopy(data)
    identities = DemandIdentities(data, rules=[rule])
    assert identities.identity(rule, "project") == digest(["rule", "project", "project"])
    assert data == before


@pytest.mark.parametrize(
    "collection", ["accessory_allocations", "included_allocations", "accessory_choices"]
)
def test_qualified_identity_survives_removing_other_revision(collection):
    from presales.configuration.projects.calculation.demand_identity import DemandIdentities

    old = dict(id="rule", revision=1, calculation_scope="room")
    current = dict(old, revision=2)
    data = dict(devices=[])
    qualified = DemandIdentities(data, rules=[old, current]).identity(old, "room-id")
    data[collection] = [dict(demand_id=qualified)]
    assert DemandIdentities(data, rules=[old]).identity(old, "room-id") == qualified
