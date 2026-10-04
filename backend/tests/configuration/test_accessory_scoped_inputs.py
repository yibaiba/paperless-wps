"""Scope input identity must survive projection; equal values are not equal owners."""

from copy import deepcopy

import pytest

from .conftest import post
from .test_accessory_demands import accessory_rule

KEY = "face_terminal_count"


def parameter(value):
    return dict(key=KEY, kind="number", value=value, unit="")


def scenario(client, catalog, config, *, scope, runtime="zen-v1"):
    rule = accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        schema_version=2,
        quantity_review="confirmed",
        quantity_evidence="隔离按范围计量",
        quantity_source="environment",
        quantity_key=KEY,
        calculation_scope=scope,
        factor="1",
    )
    data = deepcopy(config)
    data.update(calculation_version=3, decision_runtime=runtime)
    data["requirements"][0]["resources"] = []
    data["devices"].append(dict(data["devices"][0], id="device-2"))
    data["requirements"].append(dict(data["requirements"][0], id="r2", device_id="device-2"))
    return data, rule


def demand(client, data, rule):
    checked = post(client, "/check", dict(configuration=data))
    return next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])


@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
def test_one_system_input_is_counted_once_for_multiple_devices(client, catalog, config, runtime):
    data, rule = scenario(client, catalog, config, scope="system", runtime=runtime)
    data["systems"][0]["inputs"] = [parameter("3")]
    result = demand(client, data, rule)
    assert result["required"] == "3"
    assert set(result["consumer_requirement_ids"]) == {"r1", "r2"}
    assert {i["input_scope"] for i in result["quantity_inputs"]} == {"system"}
    assert {i["input_scope_id"] for i in result["quantity_inputs"]} == {"paper"}
    assert [i["reused"] for i in result["quantity_inputs"]] == [False, True]
    assert [i["input_value"] for i in result["quantity_inputs"]] == ["3", "3"]
    assert [i["value"] for i in result["quantity_inputs"]] == ["3", "0"]
    assert data["requirements"][0]["environment"] == []


@pytest.mark.parametrize("scope", ["room", "project"])
@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
def test_scoped_input_is_read_from_its_actual_location(client, catalog, config, scope, runtime):
    data, rule = scenario(client, catalog, config, scope=scope, runtime=runtime)
    data["requirements"][1]["system_id"] = "booking"
    data["room_inputs"] = {"room": [parameter("3")]}
    data["project_inputs"] = [parameter("7")]
    result = demand(client, data, rule)
    assert result["required"] == ("3" if scope == "room" else "7")


def test_same_value_in_two_systems_is_two_distinct_inputs(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="project")
    data["requirements"][1]["system_id"] = "booking"
    for system in data["systems"]:
        system["inputs"] = [parameter("3")]
    assert demand(client, data, rule)["required"] == "6"


@pytest.mark.parametrize("value,expected", [("0", "0"), (None, None)])
def test_explicit_scope_zero_and_unknown_do_not_use_role_values(
    client, catalog, config, value, expected
):
    data, rule = scenario(client, catalog, config, scope="room")
    data["room_inputs"] = {"room": [parameter(value)]}
    for requirement in data["requirements"]:
        requirement["environment"] = [dict(parameter("4"), purpose="project_input")]
    assert demand(client, data, rule)["required"] == expected


def test_conflicting_scope_and_role_values_cannot_produce_applicable_quantity(
    client, catalog, config
):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter("3")]
    data["requirements"][1]["environment"] = [dict(parameter("4"), purpose="project_input")]
    result = demand(client, data, rule)
    assert result["status"] == "conflict" and result["required"] is None


def test_legacy_role_inputs_remain_separate(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    for requirement in data["requirements"]:
        requirement["environment"] = [dict(parameter("3"), purpose="project_input")]
    assert demand(client, data, rule)["required"] == "6"


@pytest.mark.parametrize(
    "scope,identity", [("system", "paper"), ("room", "room"), ("project", "project")]
)
def test_missing_input_points_to_the_declared_scope(client, catalog, config, scope, identity):
    data, rule = scenario(client, catalog, config, scope=scope)
    result = demand(client, data, rule)
    assert result["status"] == "unknown" and result["required"] is None
    assert {i["input_scope"] for i in result["quantity_inputs"]} == {scope}
    assert {i["input_scope_id"] for i in result["quantity_inputs"]} == {identity}


def test_equal_room_inputs_remain_separate_demands(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="room")
    data["rooms"].append(dict(id="second-room", name="测试会议室"))
    data["systems"][1]["room_id"] = "second-room"
    data["requirements"][1]["system_id"] = "booking"
    data["room_inputs"] = {identity: [parameter("3")] for identity in ("room", "second-room")}
    checked = post(client, "/check", dict(configuration=data))
    results = [d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"]]
    assert {d["scope_id"]: d["required"] for d in results} == {"room": "3", "second-room": "3"}


def test_device_scope_still_counts_once_per_device(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="device")
    data["systems"][0]["inputs"] = [parameter("3")]
    checked = post(client, "/check", dict(configuration=data))
    results = [d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"]]
    assert {d["scope_id"]: d["required"] for d in results} == {"device-1": "3", "device-2": "3"}


@pytest.mark.parametrize("scope", ["room", "project"])
def test_scoped_units_are_checked_and_recheck_keeps_inputs(client, catalog, config, scope):
    data, rule = scenario(client, catalog, config, scope=scope)
    inputs = [dict(parameter("3"), kind="quantity", unit="台")]
    if scope == "room":
        data["room_inputs"] = {"room": inputs}
    else:
        data["project_inputs"] = inputs
    original = deepcopy(data)
    result = demand(client, data, rule)
    assert result["status"] == "unknown" and result["required"] is None
    assert all("单位" in i["error"] for i in result["quantity_inputs"])
    assert demand(client, data, rule) == result
    assert data == original


def test_duplicate_input_does_not_hide_later_conflict(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter("3")]
    data["requirements"][1]["environment"] = [dict(parameter("4"), purpose="project_input")]
    result = demand(client, data, rule)
    assert result["status"] == "conflict" and result["required"] is None
    assert result["quantity_inputs"][1]["reused"]
    assert result["quantity_inputs"][1]["error"]
    data["devices"].reverse()
    reversed_result = demand(client, data, rule)
    assert reversed_result["status"] == "conflict" and reversed_result["required"] is None
