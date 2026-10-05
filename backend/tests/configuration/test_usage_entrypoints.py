"""All current calculation entrypoints share the physical reservation budget."""

from copy import deepcopy

import pytest

from .conftest import BASE, post
from .test_accessory_capacity_partitions import memory_checks, pooled_project


def direct_use(data, *, quantity, amount="150"):
    data["requirements"].append(
        dict(
            id="direct",
            system_id="booking",
            role="独立服务器",
            allocations=[dict(device_id="pool", quantity=quantity, evidence="隔离分配")],
            resources=[dict(key="memory", amount=amount, unit="GB", capacity_basis="unit")],
        )
    )


@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
def test_direct_and_accessory_reservations_share_one_budget(client, catalog, config, runtime):
    data, _ = pooled_project(client, catalog, config, runtime=runtime)
    direct_use(data, quantity="2")
    checked = post(client, "/check", dict(configuration=data))
    conflicts = [c for c in checked["checks"] if c.get("code") == "device_quantity_overallocated"]
    assert len(conflicts) == 1 and conflicts[0]["device_id"] == "pool"
    assert conflicts[0]["allocated"] == "4" and conflicts[0]["available"] == "3"
    assert {"direct", "r1", "r2"} <= set(conflicts[0]["requirement_ids"])


def test_mixed_direct_and_accessory_capacity_is_partitioned(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    direct_use(data, quantity="1")
    before = deepcopy(data)
    checked = post(client, "/check", dict(configuration=data))
    checks = memory_checks(checked)
    assert len(checks) == 3 and all(c["capacity"] == "128" for c in checks)
    assert next(c for c in checks if c["requirement_ids"] == ["direct"])["status"] == "conflict"
    assert all(c["allocation_group_id"] for c in checks)
    assert data == before


def test_apply_cannot_reuse_stock_already_assigned_to_direct_roles(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    data["accessory_allocations"] = []
    direct_use(data, quantity="3")
    checked = post(client, "/check", dict(configuration=data))
    demand = next(d for d in checked["suggestions"] if d["need_key"] == "server")
    response = client.post(
        BASE + "/apply",
        json=dict(
            configuration=checked["configuration"],
            fingerprint=checked["fingerprint"],
            suggestion_id=demand["id"],
            existing_device_id="pool",
            quantity="1",
        ),
    )
    assert response.status_code == 422 and "可分配数量不足" in response.text
