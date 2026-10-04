"""Equivalent numeric representations must not change input or fulfillment status."""

from copy import deepcopy
from decimal import Decimal

import pytest

from presales.configuration.projects.planning.questions import check_questions

from .conftest import post
from .test_accessory_scoped_inputs import parameter, scenario


def accessory(checked, rule):
    return next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])


@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
@pytest.mark.parametrize("system_value,role_value", [("3", "3.00"), ("0.0", "0"), ("1.50", "1.5")])
def test_equal_numeric_system_and_role_inputs_are_not_conflicts(
    client, catalog, config, runtime, system_value, role_value
):
    data, rule = scenario(client, catalog, config, scope="system", runtime=runtime)
    data["systems"][0]["inputs"] = [parameter(system_value)]
    data["requirements"][0]["environment"] = [dict(parameter(role_value), purpose="project_input")]
    before = deepcopy(data)
    checked = post(client, "/check", dict(configuration=data))
    demand = accessory(checked, rule)
    assert demand["status"] == "pass", demand["missing_information"]
    assert not any(
        c["kind"] == "project_input" and c["status"] == "conflict" for c in checked["checks"]
    )
    assert Decimal(demand["required"]) == Decimal(system_value)
    assert demand["input_issues"] == []
    assert data == before
    assert checked["configuration"]["systems"][0]["inputs"][0]["value"] == system_value
    assert checked["configuration"]["requirements"][0]["environment"][0]["value"] == role_value


@pytest.mark.parametrize("quantity", ["3.0", "3.00"])
def test_fully_allocated_decimal_accessory_has_no_proposal_gap(client, catalog, config, quantity):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter("3")]
    checked = post(client, "/check", dict(configuration=data))
    demand = accessory(checked, rule)
    applied = post(
        client,
        "/apply",
        dict(
            configuration=checked["configuration"],
            fingerprint=checked["fingerprint"],
            suggestion_id=demand["id"],
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity=quantity,
        ),
    )
    fulfilled = accessory(applied, rule)
    assert fulfilled["status"] == "pass" and Decimal(fulfilled["missing"]) == 0
    gaps = [q for q in check_questions(applied) if q["code"].startswith("accessory_")]
    assert gaps == [], gaps


@pytest.mark.parametrize("system_value,role_value", [("3", "3.01"), (None, "0"), ("3", "-3")])
def test_distinct_numeric_or_unknown_values_remain_conflicts(
    client, catalog, config, system_value, role_value
):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter(system_value)]
    data["requirements"][0]["environment"] = [dict(parameter(role_value), purpose="project_input")]
    demand = accessory(post(client, "/check", dict(configuration=data)), rule)
    assert demand["status"] == "conflict" and demand["required"] is None


def test_equal_numbers_in_different_units_remain_conflict(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter("3")]
    data["requirements"][0]["environment"] = [
        dict(parameter("3.00"), kind="quantity", unit="台", purpose="project_input")
    ]
    demand = accessory(post(client, "/check", dict(configuration=data)), rule)
    assert demand["status"] == "conflict" and demand["required"] is None


@pytest.mark.parametrize(
    "kind,left,right",
    [
        ("text", "3", "3.00"),
        ("text", "Windows", "Linux"),
        ("enum", ["Windows"], ["Linux"]),
    ],
)
def test_non_numeric_inputs_keep_their_original_comparison(client, config, kind, left, right):
    data = deepcopy(config)
    data.update(calculation_version=3, decision_runtime="zen-v1")
    data["systems"][0]["inputs"] = [dict(key="os", kind=kind, value=left, unit="")]
    data["requirements"][0]["environment"] = [dict(key="os", kind=kind, value=right, unit="")]
    checked = post(client, "/check", dict(configuration=data))
    assert any(
        c["kind"] == "project_input" and c["status"] == "conflict" for c in checked["checks"]
    )


def test_unknown_on_both_scopes_remains_missing_instead_of_zero(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter(None)]
    data["requirements"][0]["environment"] = [dict(parameter(None), purpose="project_input")]
    checked = post(client, "/check", dict(configuration=data))
    demand = accessory(checked, rule)
    assert demand["status"] == "unknown" and demand["required"] is None
    assert {i["code"] for i in demand["input_issues"]} == {"quantity_input_missing"}


def test_small_decimal_shortfall_is_not_rounded_away(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter("3")]
    checked = post(client, "/check", dict(configuration=data))
    demand = accessory(checked, rule)
    applied = post(
        client,
        "/apply",
        dict(
            configuration=checked["configuration"],
            fingerprint=checked["fingerprint"],
            suggestion_id=demand["id"],
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity="2.999",
        ),
    )
    assert Decimal(accessory(applied, rule)["missing"]) == Decimal("0.001")
    assert any(q["code"] == "accessory_incomplete" for q in check_questions(applied))
