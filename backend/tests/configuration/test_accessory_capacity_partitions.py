"""Consumed accessory quantities cannot borrow capacity from unallocated devices."""

from copy import deepcopy

import pytest

from .conftest import post
from .test_evolution import modern_rule


def pooled_project(client, catalog, config, *, same_system=False, runtime="zen-v1"):
    data = deepcopy(config)
    data.update(calculation_version=3, decision_runtime=runtime)
    data["devices"].append(dict(data["devices"][0], id="device-2"))
    data["requirements"].append(dict(data["requirements"][0], id="r2", device_id="device-2"))
    rule = modern_rule(
        client,
        catalog["variants"][0],
        kind="accessory",
        system="",
        role="",
        need_key="server",
        target_variant_ids=[catalog["variants"][1]["id"]],
        calculation_scope="system",
        mode="per_group",
        factor="1",
        quantity_review="confirmed",
        quantity_evidence="隔离每系统一台",
        allocation_mode="consumable",
        resource_policy="required",
        output_kind="hardware",
    )
    for index, requirement in enumerate(data["requirements"]):
        if index and not same_system:
            requirement["system_id"] = "booking"
        requirement["resources"] = [
            dict(
                key="memory",
                amount="150" if not index else "40",
                unit="GB",
                capacity_basis="unit",
                applies_to="accessory",
                target_need_key="server",
            )
        ]
    data["devices"].append(
        dict(
            id="pool",
            name="隔离服务器批次",
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity="3",
            kind="hardware",
        )
    )
    checked = post(client, "/check", dict(configuration=data))
    demands = [d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"]]
    data = checked["configuration"]
    data["accessory_allocations"] = [
        dict(
            id="a-" + demand["id"],
            demand_id=demand["id"],
            device_id="pool",
            quantity="1",
            evidence="隔离按系统独立分配，不是共用服务器",
        )
        for demand in demands
    ]
    return data, demands


def memory_checks(checked):
    return [
        c
        for c in checked["checks"]
        if c["kind"] == "capacity"
        and c.get("device_id") == "pool"
        and c.get("resource") == "memory"
    ]


@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
@pytest.mark.parametrize("aggregation", ["sum", "max"])
def test_each_consumed_group_uses_only_its_assigned_units(
    client, catalog, config, runtime, aggregation
):
    data, demands = pooled_project(client, catalog, config, runtime=runtime)
    for requirement in data["requirements"]:
        requirement["resources"][0]["aggregation"] = aggregation
    before = deepcopy(data)
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["required"], c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("150", "128", "conflict"),
        ("40", "128", "pass"),
    ]
    assert {c["demand_id"] for c in memory_checks(checked)} == {d["id"] for d in demands}
    assert data == before
    assert [c["action"]["requirement_ids"] for c in memory_checks(checked)] == [["r1"], ["r2"]]
    assert not any(
        c["kind"] == "sharing" and c.get("device_id") == "pool" for c in checked["checks"]
    )


def test_one_demand_combines_its_consumers_without_multiplying_capacity(client, catalog, config):
    data, demands = pooled_project(client, catalog, config, same_system=True)
    assert len(demands) == 1
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["required"], c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("190", "128", "conflict"),
    ]
    assert memory_checks(checked)[0]["requirement_ids"] == ["r1", "r2"]


def test_capacity_changes_only_with_the_assigned_quantity(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    data["accessory_allocations"][0]["quantity"] = "2"
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("256", "pass"),
        ("128", "pass"),
    ]
    data["devices"][-1]["quantity"] = "5"
    again = post(client, "/check", dict(configuration=data))
    assert memory_checks(again) == memory_checks(checked)


def test_inconsistent_units_still_conflict_before_partitioning(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    data["requirements"][1]["resources"][0]["unit"] = "MB"
    checked = post(client, "/check", dict(configuration=data))
    assert len(memory_checks(checked)) == 1
    assert memory_checks(checked)[0]["status"] == "conflict"


def test_deployment_basis_keeps_existing_scope(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    for requirement in data["requirements"]:
        requirement["resources"][0]["capacity_basis"] = "deployment"
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["required"], c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("190", "128", "conflict"),
    ]


def test_fragmented_allocation_counts_once_per_need(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    first = data["accessory_allocations"][0]
    first["quantity"] = "0.25"
    data["accessory_allocations"].append(dict(first, id="remainder", quantity="0.75"))
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("128.00", "conflict"),
        ("128", "pass"),
    ]


def test_host_role_quantity_does_not_become_accessory_capacity(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    first = data["requirements"][0]
    first["allocations"] = [dict(device_id=first["device_id"], quantity="0.5", evidence="隔离分配")]
    first["device_id"] = None
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("128", "conflict"),
        ("128", "pass"),
    ]
    assert memory_checks(checked)[0]["requirement_ids"] == ["r1"]


def test_unknown_unit_capacity_is_not_satisfied_by_other_partitions(client, catalog, config):
    data, _ = pooled_project(client, catalog, config)
    for requirement in data["requirements"]:
        requirement["resources"][0]["unit"] = "MB"
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        (None, "unknown"),
        (None, "unknown"),
    ]
