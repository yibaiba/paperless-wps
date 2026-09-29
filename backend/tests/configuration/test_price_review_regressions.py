from copy import deepcopy
from uuid import uuid4

from presales.catalog_updates.impacts import pending_reviews

from .test_catalog_updates import COLUMN, batch_for, call, decision, edit, publish
from .test_price_adoption import prepare, price_preview


def apply_batch(client, batch):
    request = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", request)
    return call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**request, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
    )


def test_manual_new_configuration_has_authored_source_and_can_quote(client, catalog, config):
    original = catalog["variants"][0]
    fields = {k: v for k, v in original.items() if k not in {"id", "revision", "updated_at"}}
    fields.update(
        name="人工新配置", attributes=[dict(key="memory", kind="quantity", value="96", unit="GB")]
    )
    value = decision(
        original, variant=fields, manual_unit="台", manual_specification="人工确认 96GB"
    )
    value["action"] = "new_variant"
    result = apply_batch(client, edit(client, batch_for(client, original), value))
    identity = result["rows"][0]["result_variant_id"]
    variant = next(
        v for v in client.get("/api/configuration/variants").json() if v["id"] == identity
    )
    assert len(variant["source_ids"]) == 1
    source = client.get("/api/products/" + variant["source_ids"][0]).json()
    assert source["source_kind"] == "manual" and source["sources"] == {}
    assert source["provenance"]["evidence"] == value["evidence"]
    assert source["specification"] == "人工确认 96GB"
    config["devices"][0].update(variant_id=identity, source_id=source["id"])
    data = prepare(client, config)
    assert data["devices"][0]["source_snapshot"]["unit"] == "台"
    assert data["devices"][0]["source_snapshot"]["prices"] == {}
    publish(client, variant, amount="123")
    assert price_preview(client, data)["rows"][0]["price"]["amount"] == "123"


def test_partial_prices_are_resumable_without_republishing_completed_columns(client, catalog):
    variant = catalog["variants"][0]
    value = decision(
        variant,
        prices=[
            dict(column=COLUMN, state="amount", amount="11", effective_date="2026-09-29"),
            dict(column="甲方指导价", state="keep", effective_date="2026-09-29"),
        ],
    )
    first = apply_batch(client, edit(client, batch_for(client, variant), value))
    row = first["rows"][0]
    assert row["state"] == "partial"
    assert len(row["decision"]["prices"]) == 1
    row["decision"]["prices"][0].update(state="amount", amount="22")
    final = apply_batch(client, edit(client, first, row["decision"]))
    assert final["rows"][0]["state"] == "applied"
    prices = client.get("/api/catalog-updates/prices/" + variant["id"]).json()["current"]
    assert prices[COLUMN]["amount"] == "11" and prices[COLUMN]["revision"] == 1
    assert prices["甲方指导价"]["amount"] == "22"
    waiting = decision(
        variant, prices=[dict(column=COLUMN, state="keep", effective_date="2026-09-29")]
    )
    deferred = apply_batch(client, edit(client, batch_for(client, variant), waiting))
    assert deferred["rows"][0]["state"] == "deferred"
    assert edit(client, deferred, waiting)["revision"] == deferred["revision"] + 1


def test_review_is_scoped_to_actual_usage_and_fixed_rule_revision():
    variant = dict(
        id="v",
        category="",
        series=[],
        review_requirements=[dict(id="a", revision=1), dict(id="b", revision=1)],
    )
    base = dict(
        kind="suitability",
        status="confirmed",
        selector=dict(variant_ids=["v"], exclude_variant_ids=[], category="", series=[]),
        role="服务端",
    )
    a = dict(base, id="a", revision=2, system="无纸化", reviewed_variant_ids=["v"])
    b = dict(base, id="b", revision=1, system="会议预约", reviewed_variant_ids=[])
    assert pending_reviews(variant, [a, b], uses=[dict(system="无纸化", role="服务端")]) == []
    assert pending_reviews(variant, [a, b], uses=[dict(system="会议预约", role="服务端")]) == [
        dict(id="b", revision=1)
    ]
    pinned = dict(a, revision=1, reviewed_variant_ids=[])
    assert pending_reviews(variant, [pinned, b], uses=[dict(system="无纸化", role="服务端")]) == [
        dict(id="a", revision=1)
    ]
    assert (
        pending_reviews(
            variant, [dict(b, status="disabled")], uses=[dict(system="会议预约", role="服务端")]
        )
        == []
    )


def test_full_configuration_rejects_unadopted_obsolete_price(client, catalog, config):
    variant = catalog["variants"][0]
    publish(client, variant, amount="5", day="2026-08-01")
    data = prepare(client, config)
    old = price_preview(client, data)["rows"][0]["price"]
    publish(client, variant, amount=None, state="inquiry", day="2026-09-01")
    forged = deepcopy(data)
    forged["quotation"]["prices"][0].update(
        mode="version",
        unit_price="5",
        price_reference=dict(
            id=old["id"],
            revision=old["revision"],
            adopted_on="2026-09-29",
            configuration_hash=old["configuration_hash"],
        ),
    )
    result = client.post("/api/configuration/check", json=dict(configuration=forged))
    assert result.status_code == 422 and "生效修订" in result.text


def test_unrelated_sharing_review_does_not_block_current_systems():
    variant = dict(
        id="v",
        series=[],
        review_requirements=[dict(id="ab", revision=1), dict(id="cd", revision=1)],
    )
    base = dict(
        kind="sharing",
        status="confirmed",
        selector=dict(variant_ids=["v"], exclude_variant_ids=[], category="", series=[]),
    )
    ab = dict(
        base, id="ab", revision=2, shared_roles=["A/server", "B/server"], reviewed_variant_ids=["v"]
    )
    cd = dict(
        base, id="cd", revision=1, shared_roles=["C/server", "D/server"], reviewed_variant_ids=[]
    )
    uses = [
        dict(system=s, role="server", system_definition_id=s, role_id="server") for s in ("A", "B")
    ]
    assert pending_reviews(variant, [ab, cd], uses=uses) == []
    ab["shared_role_refs"] = [dict(system_definition_id=s, role_id="server") for s in ("A", "B")]
    cd["shared_role_refs"] = [dict(system_definition_id=s, role_id="server") for s in ("C", "D")]
    assert pending_reviews(variant, [ab, cd], uses=uses) == []

    same_role = [dict(system="A", role="server", requirement_id=r) for r in ("room1", "room2")]
    old_ab = dict(ab, revision=1, shared_role_refs=[])
    assert pending_reviews(variant, [old_ab, cd], uses=same_role) == [dict(id="ab", revision=1)]
