import pytest

from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.projects.planning.accessories import demand_gap
from presales.configuration.projects.planning.questions import check_questions

from .conftest import BASE, post
from .test_accessory_scoped_inputs import KEY, parameter, scenario


def inspected(client, catalog, config, *, scope="system"):
    data, rule = scenario(client, catalog, config, scope=scope)
    checked = post(client, "/check", dict(configuration=data))
    demand = next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])
    return checked, demand


def test_missing_input_has_one_scoped_customer_action_for_both_consumers(client, catalog, config):
    checked, demand = inspected(client, catalog, config)
    issues = demand["input_issues"]
    assert len(issues) == 1 and demand["input_issues_only"]
    issue = issues[0]
    assert (issue["code"], issue["scope"], issue["scope_id"], issue["key"]) == (
        "quantity_input_missing",
        "system",
        "paper",
        KEY,
    )
    assert set(issue["requirement_ids"]) == {"r1", "r2"}
    questions = [q for q in check_questions(checked) if q["code"] == "accessory_quantity_input"]
    assert len(questions) == 1 and questions[0]["recipient"] == "customer"
    assert questions[0]["action"]["type"] == "edit_quantity_inputs"
    assert questions[0]["missing_fields"] == [KEY]
    assert not any(q["code"] == "accessory_incomplete" for q in check_questions(checked))
    branch = demand_gap(checked["configuration"], demand, checked["suggestions"])
    assert branch == questions[0]


def test_missing_knowledge_is_not_disguised_as_customer_input(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    payload = {key: rule[key] for key in KnowledgeInput.model_fields if key in rule}
    payload["quantity_review"] = "unreviewed"
    response = client.put(
        BASE + "/knowledge/" + rule["id"],
        json=dict(expected_revision=rule["revision"], payload=payload),
    )
    assert response.status_code == 200, response.text
    checked = post(client, "/check", dict(configuration=data))
    demand = next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])
    assert demand["input_issues"] and not demand["input_issues_only"]
    results = check_questions(checked)
    assert any(
        q["recipient"] == "customer" and q["code"] == "accessory_quantity_input" for q in results
    )
    assert any(
        q["recipient"] == "maintainer" and q["code"] == "accessory_incomplete" for q in results
    )


def test_unselected_optional_input_does_not_ask_customer(client, catalog, config):
    checked, demand = inspected(client, catalog, config)
    results = check_questions(dict(checked, suggestions=[dict(demand, selected=False)]))
    assert not any(q["code"].startswith("accessory_") for q in results)


def test_explicit_zero_resolves_customer_input_issue(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="room")
    data["room_inputs"] = {"room": [parameter("0")]}
    checked = post(client, "/check", dict(configuration=data))
    demand = next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])
    assert demand["input_issues"] == [] and not demand["input_issues_only"]
    assert not any(q["code"].startswith("accessory_") for q in check_questions(checked))


@pytest.mark.parametrize(
    "scope,targets",
    [
        ("device", {("role", "r1")}),
        ("system", {("system", "paper")}),
        ("room", {("room", "room")}),
        ("project", {("project", "project")}),
    ],
)
def test_missing_inputs_have_exact_editable_targets(client, catalog, config, scope, targets):
    _, demand = inspected(client, catalog, config, scope=scope)
    assert {(i["scope"], i["scope_id"]) for i in demand["input_issues"]} == targets


def test_conflicting_system_and_role_values_expose_both_inputs(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="system")
    data["systems"][0]["inputs"] = [parameter("3")]
    data["requirements"][1]["environment"] = [dict(parameter("4"), purpose="project_input")]
    checked = post(client, "/check", dict(configuration=data))
    demand = next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])
    assert demand["input_issues_only"] and demand["status"] == "conflict"
    assert {(i["scope"], i["scope_id"]) for i in demand["input_issues"]} == {
        ("system", "paper"),
        ("role", "r2"),
    }
    assert {i["code"] for i in demand["input_issues"]} == {"quantity_input_conflict"}


def test_unit_error_remains_a_scoped_input_issue(client, catalog, config):
    data, rule = scenario(client, catalog, config, scope="room")
    data["room_inputs"] = {"room": [dict(parameter("3"), kind="quantity", unit="台")]}
    checked = post(client, "/check", dict(configuration=data))
    demand = next(d for d in checked["suggestions"] if d["rule"]["id"] == rule["id"])
    assert demand["input_issues_only"] and demand["required"] is None
    assert demand["input_issues"][0]["code"] == "quantity_input_unit"
    assert demand["input_issues"][0]["unit"] == ""
