"""Quantity allocations are not shared device instances."""

from copy import deepcopy

import pytest

from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import BASE, post
from .test_accessory_scoped_inputs import parameter, scenario


def allocated_project(client, catalog, config, *, mode="consumable", kind="license"):
    data, rule = scenario(client, catalog, config, scope="system")
    payload = {k: rule[k] for k in KnowledgeInput.model_fields if k in rule}
    payload.update(allocation_mode=mode, output_kind=kind)
    response = client.put(
        BASE + "/knowledge/" + rule["id"],
        json={
            "expected_revision": rule["revision"],
            "payload": payload,
        },
    )
    assert response.status_code == 200, response.text
    data["systems"][0]["inputs"] = [parameter("3")]
    checked = post(client, "/check", dict(configuration=data))
    demand = next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])
    applied = post(
        client,
        "/apply",
        dict(
            configuration=checked["configuration"],
            fingerprint=checked["fingerprint"],
            suggestion_id=demand["id"],
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity="3.00",
        ),
    )
    device_id = applied["configuration"]["accessory_allocations"][0]["device_id"]
    return applied, device_id


@pytest.mark.parametrize("kind", ["license", "accessory", "hardware"])
def test_consumable_pool_has_no_shared_instance_check(client, catalog, config, kind):
    checked, identity = allocated_project(client, catalog, config, kind=kind)
    assert not any(
        c["kind"] == "sharing" and c.get("device_id") == identity for c in checked["checks"]
    )
    usage = next(u for u in checked["device_usages"] if u["device_id"] == identity)
    assert len(usage["consumers"]) == 2
    assert {c["allocation_mode"] for c in usage["consumers"]} == {"consumable"}


def test_shared_instance_still_requires_single_device_and_evidence(client, catalog, config):
    checked, identity = allocated_project(
        client, catalog, config, mode="shareable", kind="hardware"
    )
    assert any(
        c["kind"] == "sharing" and c.get("device_id") == identity and c["status"] == "conflict"
        for c in checked["checks"]
    )


def test_direct_use_of_consumable_device_does_not_bypass_sharing(client, catalog, config):
    checked, identity = allocated_project(client, catalog, config)
    data = deepcopy(checked["configuration"])
    data["requirements"].append(
        {
            "id": "direct-use",
            "system_id": "booking",
            "role": "直接使用",
            "device_id": identity,
        }
    )
    result = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "sharing" and c.get("device_id") == identity and c["status"] != "pass"
        for c in result["checks"]
    )


def test_overallocated_consumables_still_conflict(client, catalog, config):
    checked, identity = allocated_project(client, catalog, config)
    data = deepcopy(checked["configuration"])
    allocation = data["accessory_allocations"][0]
    data["accessory_allocations"].append(dict(allocation, id="duplicate-allocation"))
    result = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "accessory_allocation"
        and c.get("device_id") == identity
        and c["status"] == "conflict"
        for c in result["checks"]
    )


def test_separate_systems_consume_distinct_quantities_from_one_pool(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    data["requirements"][1]["system_id"] = "booking"
    for system in data["systems"]:
        system["inputs"] = [parameter("3")]
    data["devices"].append(
        dict(
            id="pool",
            name="隔离数量池",
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity="6",
            kind="accessory",
        )
    )
    checked = post(client, "/check", dict(configuration=data))
    demands = [d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"]]
    assert len(demands) == 2
    for demand in demands:
        checked = post(
            client,
            "/apply",
            dict(
                configuration=checked["configuration"],
                fingerprint=checked["fingerprint"],
                suggestion_id=demand["id"],
                existing_device_id="pool",
                quantity="3",
            ),
        )
    assert not any(
        c["kind"] == "sharing" and c.get("device_id") == "pool" for c in checked["checks"]
    )
    assert len(checked["configuration"]["devices"]) == 3
    assert sum(float(a["quantity"]) for a in checked["configuration"]["accessory_allocations"]) == 6
    data = deepcopy(checked["configuration"])
    next(d for d in data["devices"] if d["id"] == "pool")["quantity"] = "5"
    reduced = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "accessory_allocation"
        and c.get("device_id") == "pool"
        and c["status"] == "conflict"
        for c in reduced["checks"]
    )
