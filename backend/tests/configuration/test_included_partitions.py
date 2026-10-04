"""Bundled content follows the host units allocated to each room."""

from copy import deepcopy

import pytest

from .conftest import AUTHOR, BASE, post
from .test_evolution import modern_rule
from .test_included_content import update_variant


@pytest.fixture
def partitioned(client, catalog, config):
    host, target = catalog["variants"]
    host = update_variant(
        client,
        host,
        included_items=[
            dict(
                id="bundled",
                name="隔离随附授权",
                variant_id=target["id"],
                kind="license",
                quantity="1",
                need_keys=["client-license"],
                status="confirmed",
                evidence=AUTHOR["evidence"],
            )
        ],
    )
    modern_rule(
        client,
        host,
        kind="accessory",
        system="",
        role="",
        need_key="client-license",
        need_name="隔离双授权需求",
        target_variant_ids=[target["id"]],
        calculation_scope="system",
        mode="per_unit",
        factor="2",
        quantity_review="confirmed",
        quantity_evidence=AUTHOR["evidence"],
        output_kind="license",
        resource_policy="not_applicable",
    )
    data = deepcopy(config)
    data.update(calculation_version=3, decision_runtime="zen-v1")
    data["rooms"].append(dict(id="room2", name="隔离二号会议室"))
    data["systems"][1]["room_id"] = "room2"
    data["devices"][0]["quantity"] = "32"
    data["requirements"] = [
        dict(
            id=identity,
            system_id=system,
            role="终端",
            resources=[],
            allocations=[
                dict(device_id="device-1", quantity=quantity, evidence=AUTHOR["evidence"])
            ],
        )
        for identity, system, quantity in (("r1", "paper", "8"), ("r2", "booking", "24"))
    ]
    return post(client, "/check", dict(configuration=data))


def demand_for(result, system="paper"):
    return next(s for s in result["suggestions"] if s["scope_id"] == system)


def credit(result, *, system="paper", quantity="8", identity="credit"):
    demand = demand_for(result, system)
    offer = demand["included_offers"][0]
    return dict(
        id=identity,
        demand_id=demand["id"],
        quantity=quantity,
        evidence=AUTHOR["evidence"],
        **{
            k: offer[k]
            for k in (
                "device_id",
                "included_item_id",
                "host_variant_id",
                "host_variant_revision",
            )
        },
    )


def test_offer_only_contains_this_rooms_allocated_host_units(partitioned):
    first, second = (demand_for(partitioned, s) for s in ("paper", "booking"))
    assert (first["required"], second["required"]) == ("16", "48")
    assert first["included_offers"][0]["available"] == "8"
    assert second["included_offers"][0]["available"] == "24"


def test_other_room_bundles_cannot_hide_a_shortage(client, partitioned):
    data = dict(
        partitioned["configuration"], included_allocations=[credit(partitioned, quantity="16")]
    )
    result = post(client, "/check", dict(configuration=data))
    demand = demand_for(result)
    assert (demand["included_quantity"], demand["missing"]) == ("0", "16")
    assert demand["included_allocation_checks"][0]["status"] == "conflict"


def test_edit_rejects_credit_from_another_room(client, partitioned, project):
    response = client.post(
        BASE + "/projects/" + project["id"] + "/edit-preview",
        json=dict(
            configuration=partitioned["configuration"],
            expected_revision=0,
            draft_version=0,
            operations=[dict(action="included_link", value=credit(partitioned, quantity="16"))],
        ),
    )
    assert response.status_code == 422, response.text


def test_valid_credits_remain_independent_and_supply_does_not_change_entitlement(
    client, partitioned
):
    data = deepcopy(partitioned["configuration"])
    data["included_allocations"] = [
        credit(partitioned),
        credit(partitioned, system="booking", quantity="24", identity="other"),
    ]
    data["supply_allocations"] = [
        dict(
            id="existing",
            device_id="device-1",
            source="existing",
            quantity="32",
            evidence=AUTHOR["evidence"],
        )
    ]
    result = post(client, "/check", dict(configuration=data))
    assert [
        (demand_for(result, s)["included_quantity"], demand_for(result, s)["missing"])
        for s in ("paper", "booking")
    ] == [("8", "8"), ("24", "24")]
    assert result["project_output"]["procurement_lines"] == []
    assert all(
        c["status"] == "pass" for c in result["checks"] if c["kind"] == "included_allocation"
    )


def test_reduction_invalidates_only_local_credit_and_unlink_exposes_stale_credit(
    client, partitioned
):
    data = deepcopy(partitioned["configuration"])
    data["included_allocations"] = [credit(partitioned)]
    data["requirements"][0]["allocations"][0]["quantity"] = "4"
    result = post(client, "/check", dict(configuration=data))
    first = demand_for(result)
    check = first["included_allocation_checks"][0]
    assert (
        check["scope_capacity"],
        check["scope_allocated_quantity"],
        check["counted_quantity"],
    ) == ("4", "8", "0")
    assert (first["required"], first["missing"]) == ("8", "8")
    assert demand_for(result, "booking")["included_offers"][0]["available"] == "24"
    assert data["included_allocations"][0]["quantity"] == "8"
    data["requirements"][0]["allocations"] = []
    detached = post(client, "/check", dict(configuration=data))
    assert not any(s["scope_id"] == "paper" for s in detached["suggestions"])
    assert any(
        c["kind"] == "included_allocation" and c["status"] == "conflict" for c in detached["checks"]
    )


def test_two_demands_on_same_allocated_units_cannot_each_consume_the_bundle(client, partitioned):
    from presales.configuration.knowledge.schemas import KnowledgeInput

    rule = partitioned["configuration"]["knowledge_snapshot"][0]
    copied = post(
        client,
        "/knowledge",
        {
            **{k: v for k, v in rule.items() if k in KnowledgeInput.model_fields},
            "name": "隔离第二份授权需求",
        },
    )
    refreshed = post(
        client,
        "/check",
        dict(
            configuration=partitioned["configuration"],
            refresh_knowledge=True,
        ),
    )
    other = next(
        s
        for s in refreshed["suggestions"]
        if s["rule"]["id"] == copied["id"] and s["scope_id"] == "paper"
    )
    first = next(
        s
        for s in refreshed["suggestions"]
        if s["rule"]["id"] == rule["id"] and s["scope_id"] == "paper"
    )
    data = dict(
        refreshed["configuration"],
        included_allocations=[
            dict(credit(partitioned), demand_id=first["id"]),
            dict(credit(partitioned, identity="duplicate"), demand_id=other["id"]),
        ],
    )
    result = post(client, "/check", dict(configuration=data))
    checks = [c for c in result["checks"] if c["kind"] == "included_allocation"]
    assert len(checks) == 2 and all(c["status"] == "conflict" for c in checks)
    assert all(s["included_quantity"] == "0" for s in result["suggestions"])


@pytest.mark.parametrize("scope", ["device", "project"])
def test_combined_scope_counts_host_units_once(client, partitioned, scope):
    from presales.configuration.knowledge.schemas import KnowledgeInput

    rule = partitioned["configuration"]["knowledge_snapshot"][0]
    payload = {k: v for k, v in rule.items() if k in KnowledgeInput.model_fields}
    response = client.put(
        BASE + "/knowledge/" + rule["id"],
        json=dict(
            expected_revision=rule["revision"],
            payload={**payload, "calculation_scope": scope},
        ),
    )
    assert response.status_code == 200, response.text
    result = post(
        client, "/check", dict(configuration=partitioned["configuration"], refresh_knowledge=True)
    )
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["included_offers"][0]["available"] == "32"


def test_environment_input_is_not_treated_as_a_host_count(client, partitioned):
    from presales.configuration.knowledge.schemas import KnowledgeInput

    rule = partitioned["configuration"]["knowledge_snapshot"][0]
    payload = {k: v for k, v in rule.items() if k in KnowledgeInput.model_fields}
    response = client.put(
        BASE + "/knowledge/" + rule["id"],
        json=dict(
            expected_revision=rule["revision"],
            payload={
                **payload,
                "quantity_source": "environment",
                "quantity_key": "isolated_units",
                "quantity_unit": "",
                "factor": "1",
            },
        ),
    )
    assert response.status_code == 200, response.text
    data = deepcopy(partitioned["configuration"])
    for requirement in data["requirements"]:
        requirement["environment"] = [
            dict(key="isolated_units", kind="number", value="100", purpose="project_input")
        ]
    result = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    first = demand_for(result)
    assert first["required"] == "100"
    assert first["included_offers"][0]["available"] == "8"
