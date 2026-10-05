"""A role fulfilled by a consumed accessory references that allocation, not the pool."""

from copy import deepcopy

import pytest

from .conftest import AUTHOR, post
from .test_accessory_capacity_partitions import memory_checks, pooled_project
from .test_evolution import modern_rule


def aliased_project(client, catalog, config, *, runtime="zen-v1"):
    data, demands = pooled_project(client, catalog, config, runtime=runtime)
    definition = post(
        client,
        "/definitions",
        dict(
            name="隔离软件与服务器配套引用",
            status="confirmed",
            roles=[
                dict(id="software", name="服务端软件", output_kind="software"),
                dict(
                    id="server",
                    name="服务器",
                    output_kind="hardware",
                    fulfilled_by=dict(
                        role_id="software", need_key="server", status="confirmed", **AUTHOR
                    ),
                ),
            ],
            **AUTHOR,
        ),
    )
    data["definition_snapshot_id"] = None
    for system in data["systems"]:
        system["definition_id"] = definition["id"]
    for requirement in list(data["requirements"]):
        requirement["role_id"] = "software"
        data["requirements"].append(
            dict(
                id="alias-" + requirement["id"],
                system_id=requirement["system_id"],
                role_id="server",
                role="服务器",
                allocations=[dict(device_id="pool", quantity="1", evidence=AUTHOR["evidence"])],
            )
        )
    return data, demands


@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
def test_fulfilled_roles_keep_consumed_capacity_and_do_not_create_sharing(
    client, catalog, config, runtime
):
    data, demands = aliased_project(client, catalog, config, runtime=runtime)
    before = deepcopy(data)
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["required"], c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("150", "128", "conflict"),
        ("40", "128", "pass"),
    ]
    assert {c["demand_id"] for c in memory_checks(checked)} == {d["id"] for d in demands}
    assert not any(
        c["kind"] == "sharing" and c.get("device_id") == "pool" for c in checked["checks"]
    )
    assert data == before


def test_alias_resource_is_checked_with_its_accessory_partition(client, catalog, config):
    data, _ = aliased_project(client, catalog, config)
    data["requirements"][2]["resources"] = [
        dict(key="memory", amount="10", unit="GB", capacity_basis="unit")
    ]
    checked = post(client, "/check", dict(configuration=data))
    assert [(c["required"], c["capacity"], c["status"]) for c in memory_checks(checked)] == [
        ("160", "128", "conflict"),
        ("40", "128", "pass"),
    ]


def test_alias_does_not_hide_an_unrelated_direct_use(client, catalog, config):
    data, _ = aliased_project(client, catalog, config)
    data["requirements"].append(
        dict(id="unrelated", system_id="booking", role="额外用途", device_id="pool")
    )
    checked = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "sharing" and c.get("device_id") == "pool" and c["status"] == "conflict"
        for c in checked["checks"]
    )


def test_alias_resources_do_not_leak_to_other_needs_of_the_same_role(client, catalog, config):
    data, _ = aliased_project(client, catalog, config)
    rule = modern_rule(
        client,
        catalog["variants"][0],
        kind="accessory",
        need_key="backup",
        target_variant_ids=[catalog["variants"][1]["id"]],
        calculation_scope="system",
        mode="per_group",
        factor="1",
        quantity_review="confirmed",
        quantity_evidence=AUTHOR["evidence"],
        allocation_mode="consumable",
        resource_policy="required",
    )
    data["requirements"][0]["resources"].append(
        dict(
            key="memory",
            amount="80",
            unit="GB",
            capacity_basis="unit",
            applies_to="accessory",
            target_need_key="backup",
        )
    )
    data["requirements"][2]["resources"] = [
        dict(key="memory", amount="10", unit="GB", capacity_basis="unit")
    ]
    checked = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    demand = next(
        d
        for d in checked["suggestions"]
        if d["rule"]["id"] == rule["id"] and "r1" in d["consumer_requirement_ids"]
    )
    data = checked["configuration"]
    data["accessory_allocations"].append(
        dict(
            id="backup",
            demand_id=demand["id"],
            device_id="pool",
            quantity="1",
            evidence=AUTHOR["evidence"],
        )
    )
    checked = post(client, "/check", dict(configuration=data))
    results = memory_checks(checked)
    assert [(c["required"], c["capacity"], c["status"]) for c in results] == [
        ("160", "128", "conflict"),
        ("40", "128", "pass"),
        ("80", "128", "pass"),
    ]
    assert results[-1]["demand_id"] == demand["id"]


def test_consumers_of_the_alias_roles_own_accessories_are_not_aliased():
    from presales.configuration.projects.calculation.fulfillment import alias_consumers

    consumers = [
        dict(requirement_id="server", via="direct"),
        dict(requirement_id="server", via="accessory", demand_id="power"),
    ]
    aliases = {"server": dict(requirement_id="software", demand_ids=["host"])}
    before = deepcopy(consumers)
    usages = alias_consumers([dict(consumers=consumers)], aliases)
    direct, accessory = usages[0]["consumers"]
    assert direct["fulfilled_by_demand_ids"] == ["host"]
    assert "fulfilled_by_requirement_id" not in accessory
    assert consumers == before


def test_shared_accessory_with_aliases_still_requires_sharing_evidence(client, catalog, config):
    from .test_proposal_generation import apply, draft_for, plan, published, read

    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    # A second system explicitly reuses the same generated server.
    data["systems"].append(dict(data["systems"][0], id="second"))
    data["requirements"].extend(
        [dict(r, id="second-" + r["id"], system_id="second") for r in list(data["requirements"])]
    )
    terminal = next(
        r for r in data["requirements"] if r["system_id"] == "second" and r["role_id"] == "terminal"
    )
    original_device = next(d for d in data["devices"] if d["id"] == terminal["device_id"])
    data["devices"].append(dict(original_device, id="second-terminal"))
    terminal["device_id"] = "second-terminal"
    checked = post(client, "/check", dict(configuration=data))
    original = data["accessory_allocations"][0]
    extra = next(d for d in checked["suggestions"] if d["id"] != original["demand_id"])
    data["accessory_allocations"].append(dict(original, id="second", demand_id=extra["id"]))
    checked = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "sharing"
        and c.get("device_id") == original["device_id"]
        and c["status"] == "unknown"
        for c in checked["checks"]
    )


def test_seed_optional_alias_database(client, catalog, config, tmp_path):
    import os
    from pathlib import Path

    from .test_accessory_capacity_protocol import seed_capacity_database

    data, _ = aliased_project(client, catalog, config)
    target = Path(os.environ.get("ALIAS_BROWSER_FIXTURE", str(tmp_path / "alias.sqlite")))
    seed_capacity_database(client, data, target=target)
