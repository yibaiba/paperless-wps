"""Physical reservation invariants, independent of entrypoint or business product names."""

from copy import deepcopy
from decimal import Decimal

import pytest

from presales.configuration.projects.calculation.usage import build_usage_projection
from presales.configuration.projects.role_allocations import project_allocations


@pytest.fixture
def scenario():
    data = dict(
        rooms=[dict(id="room", name="隔离会议室")],
        systems=[dict(id="system", name="隔离系统", kind="系统", definition_id="definition")],
        devices=[dict(id="pool", quantity="3"), dict(id="software", quantity="1")],
        requirements=[
            dict(
                id="parent",
                system_id="system",
                role_id="software",
                role="软件",
                device_id="software",
                environment=[],
                resources=[],
            )
        ],
        accessory_allocations=[
            dict(id="a1", device_id="pool", demand_id="need", quantity="1", evidence="隔离")
        ],
        included_allocations=[],
    )
    demands = [
        dict(
            id="need",
            need_key="server",
            status="pass",
            consumer_requirement_ids=["parent"],
            rule=dict(
                id="rule",
                revision=1,
                allocation_mode="consumable",
                resource_policy="required",
                need_key="server",
            ),
        )
    ]
    definitions = dict(
        packages=[],
        definitions=[
            dict(
                id="definition",
                roles=[
                    dict(
                        id="server",
                        fulfilled_by=dict(
                            role_id="software", need_key="server", status="confirmed"
                        ),
                    )
                ],
            )
        ],
    )
    return data, demands, definitions


def projection(scenario):
    data, demands, definitions = scenario
    prepared, _ = project_allocations(data)
    return build_usage_projection(prepared, demands=demands, definitions=definitions)


def add_role(data, *, quantity="1", role_id="direct", identity="direct"):
    data["requirements"].append(
        dict(
            id=identity,
            system_id="system",
            role_id=role_id,
            role=role_id,
            device_id=None,
            allocations=[dict(device_id="pool", quantity=quantity, evidence="隔离")],
            environment=[],
            resources=[],
        )
    )


@pytest.mark.parametrize(
    "direct,accessory,extra", [("2", "1", "0"), ("2", "2", "1"), ("0.5", "0.25", "0")]
)
def test_direct_and_accessory_share_one_quantity_budget(scenario, direct, accessory, extra):
    data, demands, _ = scenario
    add_role(data, quantity=direct)
    data["accessory_allocations"][0]["quantity"] = accessory
    projected = projection(scenario)
    summary = projected.device("pool")["quantity_summary"]
    assert Decimal(summary["reserved_quantity"]) == Decimal(direct) + Decimal(accessory)
    assert Decimal(summary["overallocated_quantity"]) == Decimal(extra)
    assert projected.available("pool", demand=demands[0]) == max(
        Decimal("3") - Decimal(direct) - Decimal(accessory), 0
    )


def test_aliases_never_reserve_same_quantity_again(scenario):
    data, _, _ = scenario
    for identity in ("one", "two"):
        add_role(data, role_id="server", identity=identity)
    usage = projection(scenario).device("pool")
    assert usage["quantity_summary"]["reserved_quantity"] == "1"
    assert len(usage["allocation_groups"]) == 1 and len(usage["role_references"]) == 2


def test_all_parents_and_needs_are_retained_and_resource_split_is_explicit(scenario):
    data, demands, _ = scenario
    data["requirements"].append(dict(data["requirements"][0], id="parent2"))
    demands.append(dict(demands[0], id="need2", consumer_requirement_ids=["parent2"]))
    data["accessory_allocations"].append(
        dict(data["accessory_allocations"][0], id="a2", demand_id="need2")
    )
    add_role(data, role_id="server", quantity="2")
    data["requirements"][-1]["resources"] = [
        dict(key="memory", amount="150", unit="GB", capacity_basis="unit")
    ]
    usage = projection(scenario).device("pool")
    reference = usage["role_references"][0]
    assert set(reference["demand_ids"]) == {"need", "need2"}
    assert set(reference["fulfilled_by_requirement_ids"]) == {"parent", "parent2"}
    assert usage["quantity_summary"]["reserved_quantity"] == "2"
    assert any(c["code"] == "resource_split_missing" for c in usage["allocation_checks"])
    assert all(not c["resources"] for g in usage["allocation_groups"] for c in g["consumers"])


def test_single_instance_sharing_is_one_reservation(scenario):
    data, demands, _ = scenario
    data["devices"][0]["quantity"] = "1"
    demands[0]["rule"]["allocation_mode"] = "shareable"
    add_role(data)
    add_role(data, identity="other")
    usage = projection(scenario).device("pool")
    assert usage["quantity_summary"]["reserved_quantity"] == "1"
    assert usage["allocation_groups"][0]["mode"] == "shared"
    assert len(usage["allocation_groups"][0]["consumers"]) == 3


def test_projection_is_deeply_immutable_and_serialized_views_are_owned(scenario):
    before = deepcopy(scenario)
    projected = projection(scenario)
    with pytest.raises(TypeError):
        projected.device("pool")["quantity_summary"]["reserved_quantity"] = "99"
    view = projected.views()
    view[0]["allocation_groups"].clear()
    assert projected.device("pool")["allocation_groups"]
    assert scenario == before


def test_fragmented_need_reserves_sum_once_per_need(scenario):
    data, _, _ = scenario
    first = data["accessory_allocations"][0]
    first["quantity"] = "0.25"
    data["accessory_allocations"].append(dict(first, id="remainder", quantity="0.75"))
    usage = projection(scenario).device("pool")
    assert len(usage["allocation_groups"]) == 1
    assert Decimal(usage["allocation_groups"][0]["quantity"]) == 1
    assert set(usage["allocation_groups"][0]["allocation_ids"]) == {"a1", "remainder"}


def test_reference_cannot_claim_unreserved_inventory(scenario):
    data, _, _ = scenario
    add_role(data, role_id="server", quantity="2")
    checks = projection(scenario).device("pool")["allocation_checks"]
    assert any(c["code"] == "role_reference_overallocated" for c in checks)


def test_record_order_does_not_change_projection_or_fingerprint(scenario):
    data, _, _ = scenario
    add_role(data, role_id="server")
    add_role(data, role_id="server", identity="alias2")
    first = projection(scenario)
    data["requirements"].reverse()
    data["devices"].reverse()
    data["accessory_allocations"].reverse()
    second = projection(scenario)
    assert second.fingerprint == first.fingerprint
    assert sorted(second.views(), key=lambda u: u["device_id"]) == sorted(
        first.views(), key=lambda u: u["device_id"]
    )


def test_unresolved_allocation_is_visible_and_not_reused(scenario):
    data, demands, _ = scenario
    data["accessory_allocations"].append(
        dict(id="stale", device_id="pool", demand_id="gone", quantity="2")
    )
    result = projection(scenario)
    assert result.available("pool", demand=demands[0]) == 0
    group = next(g for g in result.device("pool")["allocation_groups"] if g["mode"] == "unresolved")
    assert tuple(group["allocation_ids"]) == ("stale",)


def test_one_direct_user_is_not_reported_as_shared(scenario):
    result = projection(scenario).device("software")
    assert result["quantity_summary"]["shared_quantity"] == "0"
    assert result["quantity_summary"]["independent_quantity"] == "1"
