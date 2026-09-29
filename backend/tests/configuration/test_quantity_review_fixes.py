"""Quantity regressions using isolated fixture knowledge, never business data."""

from copy import deepcopy

import pytest

from .conftest import post
from .test_accessory_demands import accessory_rule
from .test_proposal_generation import apply, draft_for, plan, published, read, write


def role_check(checked):
    return next(c for c in checked["checks"] if c["kind"] == "role_allocation")


def test_direct_binding_checks_quantity_after_edit_and_recovery(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    generated = apply(client, draft, plan(client, draft))
    config = read(client, generated)["configuration"]
    requirement, device = config["requirements"][0], config["devices"][0]
    assert requirement["device_id"] == device["id"] and not requirement["allocations"]
    current = generated
    for quantity, expected in [("1", "conflict"), ("32", "pass")]:
        current = write(
            client,
            current,
            [
                dict(action="device_patch", device_id=device["id"], quantity=quantity),
                dict(
                    action="supply_set",
                    device_id=device["id"],
                    allocations=[dict(a, quantity=quantity) for a in config["supply_allocations"]],
                ),
            ],
        )
        checked = read(client, current)["checked"]
        result = role_check(checked)
        assert (result["required"], result["allocated"], result["status"]) == (
            "32",
            quantity,
            expected,
        )
        assert checked["readiness"]["ready_for_confirmation"] == (expected == "pass")
    changed = deepcopy(read(client, current)["configuration"])
    changed["systems"][0]["inputs"][0]["value"] = "48"
    assert role_check(post(client, "/check", dict(configuration=changed)))["status"] == "conflict"


@pytest.mark.parametrize("gap", ["basis", "input"])
def test_direct_binding_missing_basis_or_input_is_unknown(client, catalog, gap):
    definition, package = published(client, catalog, quantity=gap != "basis")
    draft = draft_for(client, definition, package)
    data = read(client, draft)["configuration"]
    variant, source = catalog["variants"][0], catalog["sources"][0]
    data["devices"] = [
        dict(
            id="terminal",
            name="隔离终端",
            kind="hardware",
            quantity="32",
            variant_id=variant["id"],
            source_id=source["id"],
        )
    ]
    data["requirements"] = [
        dict(id="role", system_id="system", role="终端", role_id="terminal", device_id="terminal")
    ]
    if gap == "input":
        data["systems"][0]["inputs"] = []
    checked = post(client, "/check", dict(configuration=data))
    result = role_check(checked)
    assert result["status"] == "unknown" and result["required"] is None
    action = result["action"]
    assert action["type"] == ("edit_definition" if gap == "basis" else "edit_system_inputs")
    assert action["missing_fields"]
    assert not checked["readiness"]["ready_for_confirmation"]


def test_fulfilled_server_uses_accessory_quantity_only_when_linked(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    generated = apply(client, draft, plan(client, draft))
    result = read(client, generated)
    assert result["checked"]["readiness"]["ready_for_confirmation"]
    data = result["configuration"]
    server = next(r for r in data["requirements"] if r["role_id"] == "server")
    assert not any(
        c["kind"] == "role_allocation" and c.get("requirement_id") == server["id"]
        for c in result["checked"]["checks"]
    )
    data["accessory_allocations"] = []
    checked = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "role_allocation"
        and c.get("requirement_id") == server["id"]
        and c["status"] == "unknown"
        for c in checked["checks"]
    )
    assert not checked["readiness"]["ready_for_confirmation"]


def shared_need(client, catalog, config):
    config["calculation_version"] = 3
    rule = accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        schema_version=2,
        quantity_review="confirmed",
        quantity_evidence="隔离测试数量依据",
        allocation_mode="shareable",
        resource_policy="not_applicable",
        factor="2",
    )
    config["requirements"][0]["resources"] = []
    config["devices"].append(
        dict(
            id="server",
            name="同一台已存在的配套设备",
            kind="hardware",
            quantity="1",
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
        )
    )
    checked = post(client, "/check", dict(configuration=config))
    demand = next(s for s in checked["suggestions"] if s["rule"]["id"] == rule["id"])
    assert demand["required"] == "2"
    return checked, demand


def test_same_shareable_instance_cannot_fill_same_demand_twice(client, catalog, config):
    checked, demand = shared_need(client, catalog, config)
    request = dict(
        configuration=checked["configuration"],
        fingerprint=checked["fingerprint"],
        suggestion_id=demand["id"],
        existing_device_id="server",
        quantity="1",
    )
    first = post(client, "/apply", request)
    response = client.post(
        "/api/configuration/apply",
        json=dict(request, configuration=first["configuration"], fingerprint=first["fingerprint"]),
    )
    assert response.status_code == 422
    assert "同一配套需求" in response.text
    assert first["suggestions"][0]["missing"] == "1"


@pytest.mark.parametrize("duplicate", [True, False])
def test_recheck_detects_historical_overallocation_and_device_reduction(
    client, catalog, config, duplicate
):
    checked, demand = shared_need(client, catalog, config)
    data = checked["configuration"]
    allocation = dict(
        id="allocation",
        demand_id=demand["id"],
        device_id="server",
        quantity="1" if duplicate else "2",
        evidence="隔离测试",
    )
    data["accessory_allocations"] = [allocation]
    if duplicate:
        data["accessory_allocations"].append(dict(allocation, id="second"))
    result = post(client, "/check", dict(configuration=data))
    need = next(s for s in result["suggestions"] if s["id"] == demand["id"])
    assert (need["status"], need["existing"], need["missing"]) == ("conflict", "0", "2")
    assert any(
        c["kind"] == "accessory_allocation" and c["status"] == "conflict" for c in result["checks"]
    )
    assert result["configuration"]["accessory_allocations"] == data["accessory_allocations"]
    data["accessory_allocations"] = [dict(allocation, quantity="1")]
    fixed = post(client, "/check", dict(configuration=data))
    need = next(s for s in fixed["suggestions"] if s["id"] == demand["id"])
    assert (need["status"], need["existing"], need["missing"]) == ("pass", "1", "1")


@pytest.mark.parametrize("packaged", [True, False])
def test_role_quantity_uses_pinned_definition_until_explicit_refresh(client, catalog, packaged):
    from presales.configuration.definitions.schemas import SystemDefinition

    from .test_evolution_versions import editable

    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    generated = apply(client, draft, plan(client, draft))
    data = read(client, generated)["configuration"]
    if not packaged:
        data["systems"][0]["knowledge_package_id"] = ""
    baseline = post(client, "/check", dict(configuration=data))
    payload = editable(SystemDefinition, definition)
    payload["roles"][0]["quantity_basis"]["factor"] = "2"
    response = client.put(
        "/api/configuration/definitions/" + definition["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert response.status_code == 200, response.text
    frozen = post(client, "/check", dict(configuration=baseline["configuration"]))
    assert role_check(frozen)["required"] == "32"
    refreshed = post(
        client, "/check", dict(configuration=baseline["configuration"], refresh_knowledge=True)
    )
    assert role_check(refreshed)["required"] == ("32" if packaged else "64")
    assert role_check(refreshed)["status"] == ("pass" if packaged else "conflict")


def test_partial_fulfilled_role_does_not_hide_unlinked_split(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    generated = apply(client, draft, plan(client, draft))
    data = read(client, generated)["configuration"]
    requirement = next(r for r in data["requirements"] if r["role_id"] == "server")
    server = next(d for d in data["devices"] if d["id"] == requirement["device_id"])
    data["devices"].append(dict(server, id="unlinked"))
    requirement.update(
        device_id=None,
        allocations=[
            dict(device_id=server["id"], quantity="1", evidence="隔离测试已关联配套"),
            dict(device_id="unlinked", quantity="1", evidence="隔离测试未关联配套"),
        ],
    )
    result = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "role_allocation"
        and c.get("requirement_id") == requirement["id"]
        and c["status"] == "unknown"
        for c in result["checks"]
    )
    assert not result["readiness"]["ready_for_confirmation"]


def test_shareable_batch_allows_remaining_capacity_and_completed_retry(client, catalog, config):
    checked, demand = shared_need(client, catalog, config)
    data = checked["configuration"]
    next(d for d in data["devices"] if d["id"] == "server")["quantity"] = "2"
    checked = post(client, "/check", dict(configuration=data))
    for missing in ["1", "0", "0"]:
        checked = post(
            client,
            "/apply",
            dict(
                configuration=checked["configuration"],
                fingerprint=checked["fingerprint"],
                suggestion_id=demand["id"],
                existing_device_id="server",
                quantity="1",
            ),
        )
        need = next(s for s in checked["suggestions"] if s["id"] == demand["id"])
        assert need["status"] == "pass" and need["missing"] == missing
    assert len(checked["configuration"]["accessory_allocations"]) == 2
    assert (
        next(d for d in checked["configuration"]["devices"] if d["id"] == "server")["quantity"]
        == "2"
    )
