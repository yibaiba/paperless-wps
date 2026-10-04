"""Isolated multi-room charging checks: allocation does not pool spare capacity."""

from copy import deepcopy

import pytest
import zen
from presales.configuration.projects.repository import ProjectConfigurations
from presales.configuration.projects.schemas import Configuration
from presales.rules.engine import ZenQuantityEngine

from .distributed_charging import build_charging_plan
from .maintenance import apply_plan
from .test_distributed_charging import (
    base_session,  # noqa: F401
    check,
    config,
)
from .test_distributed_charging import session as charging_session  # noqa: F401


@pytest.fixture
def session(charging_session):  # noqa: F811
    return charging_session


def two_rooms(session, *, demands, layout="independent", total="2"):
    apply_plan(session, build_charging_plan(session))
    data = config(session, demand=demands[0]).model_dump(mode="json")
    data["rooms"].append(dict(id="room2", name="隔离二号会议室"))
    other = deepcopy(data["systems"][0])
    other.update(id="system2", room_id="room2", name="隔离分布式二")
    other["inputs"][0]["value"] = demands[1]
    data["systems"].append(other)
    role = dict(deepcopy(data["requirements"][0]), id="need2", system_id="system2")
    data["requirements"].append(role)
    if layout == "independent":
        data["devices"].append(dict(deepcopy(data["devices"][0]), id="cart2"))
        role["device_id"] = "cart2"
    elif layout == "partitioned":
        data["devices"][0]["quantity"] = total
        for requirement in data["requirements"]:
            requirement.update(
                device_id=None,
                allocations=[
                    dict(
                        device_id="cart",
                        quantity="1",
                        evidence="隔离：每个房间明确分配一台",
                    )
                ],
            )
    return Configuration.model_validate(data)


def limits(result):
    return [c for c in result["checks"] if c.get("resource") == "charging_capacity"]


def test_independent_same_model_rooms_keep_distinct_capacities(session):
    result = check(session, two_rooms(session, demands=("32", "48")))
    assert {c["device_id"]: (c["status"], c["capacity"]) for c in limits(result)} == {
        "cart": ("pass", "36"),
        "cart2": ("conflict", "36"),
    }
    assert len(result["project_output"]["lines"]) == 2


@pytest.mark.parametrize("total", ["2", "3"])
def test_partitioned_batch_cannot_lend_spare_capacity_between_rooms(session, total):
    result = check(
        session, two_rooms(session, demands=("48", "12"), layout="partitioned", total=total)
    )
    checks = limits(result)
    assert len(checks) == 2
    assert {
        tuple(c["requirement_ids"]): (c["required"], c["capacity"], c["status"]) for c in checks
    } == {
        ("need",): ("48", "36", "conflict"),
        ("need2",): ("12", "36", "pass"),
    }
    assert len(result["project_output"]["lines"]) == 1
    assert not any(c["kind"] == "sharing" for c in result["checks"])


@pytest.mark.parametrize("demand,expected", [("16", "pass"), ("20", "conflict")])
def test_single_shared_cart_sums_demand_but_keeps_sharing_unknown(session, demand, expected):
    result = check(session, two_rooms(session, demands=(demand, demand), layout="shared"))
    assert len(limits(result)) == 1
    assert limits(result)[0]["status"] == expected
    assert limits(result)[0]["capacity"] == "36"
    assert any(c["kind"] == "sharing" and c["status"] == "unknown" for c in result["checks"])
    assert len(result["project_output"]["lines"]) == 1


def test_two_different_cart_models_require_explicit_resource_distribution(session):
    apply_plan(session, build_charging_plan(session))
    data = config(session, demand="48").model_dump(mode="json")
    smaller = config(session, row=32).model_dump(mode="json")["devices"][0]
    data["devices"].append(dict(smaller, id="small"))
    data["requirements"][0].update(
        device_id=None,
        allocations=[
            dict(device_id=i, quantity="1", evidence="隔离：选定两种规格")
            for i in ("cart", "small")
        ],
    )
    result = check(session, Configuration.model_validate(data))
    assert not limits(result)
    assert any(
        c["code"] == "role_resource_distribution" and c["status"] == "unknown"
        for c in result["checks"]
    )
    assert len(result["project_output"]["lines"]) == 2


def test_existing_cart_participates_in_capacity_without_purchase(session):
    apply_plan(session, build_charging_plan(session))
    data = config(session).model_dump(mode="json")
    data["supply_allocations"] = [
        dict(
            id="existing",
            device_id="cart",
            quantity="1",
            source="existing",
            evidence="隔离测试：客户明确已有",
        )
    ]
    result = check(session, Configuration.model_validate(data))
    assert limits(result)[0]["status"] == "pass"
    assert result["project_output"]["procurement_lines"] == []


def test_explicit_upgrade_only_changes_the_new_snapshot(session):
    old = check(session, config(session, demand="48"))["configuration"]
    apply_plan(session, build_charging_plan(session))
    repository = ProjectConfigurations(session, ZenQuantityEngine(zen.ZenEngine()))
    before = deepcopy(old)
    latest = repository.check(Configuration.model_validate(old), refresh=True)
    assert limits(latest)[0]["status"] == "conflict"
    assert old == before
    assert not limits(check(session, Configuration.model_validate(old)))
