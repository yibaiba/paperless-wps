"""Project and candidate combination checks use the same system input projection."""

from copy import deepcopy

import pytest

from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import BASE, knowledge, post
from .test_evolution_versions import editable
from .test_zen_combinations import add_target, setup


@pytest.mark.parametrize(
    "os_name,expected", [("Windows", "conflict"), ("Linux", "pass"), (None, "unknown")]
)
def test_candidate_uses_system_inputs_for_combination_activation(
    client, catalog, config, os_name, expected
):
    data, rule = setup(client, catalog, config, mode="exclude")
    payload = editable(KnowledgeInput, rule)
    payload["activation_conditions"] = [dict(field="project.os", operator="eq", value="Windows")]
    updated = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert updated.status_code == 200, updated.text
    knowledge(
        client,
        catalog["variants"][0],
        schema_version=2,
        role="main",
        role_id="main",
        system_definition_id=data["systems"][0]["definition_id"],
    )
    inputs = [] if os_name is None else [dict(key="os", value=os_name, kind="text", unit="")]
    data["systems"][0]["inputs"] = inputs
    add_target(data, catalog)
    project = post(client, "/check", dict(configuration=data))
    expected_checks = [c for c in project["checks"] if c["kind"] == "combination"]
    assert [c["status"] for c in expected_checks] == ([] if os_name == "Linux" else [expected])

    unselected = deepcopy(project["configuration"])
    unselected["devices"] = [d for d in unselected["devices"] if d["id"] != "device-1"]
    unselected["requirements"][0]["device_id"] = None
    candidates = post(
        client,
        "/candidates",
        dict(
            configuration=unselected,
            requirement_id="r1",
            system="无纸化",
            role="main",
            role_id="main",
            system_definition_id=data["systems"][0]["definition_id"],
            environment=[dict(p, purpose="project_input") for p in inputs],
            include_all=True,
        ),
    )
    candidate = next(c for c in candidates if c["variant"]["id"] == catalog["variants"][0]["id"])
    assert candidate["status"] == expected
    assert [c["status"] for c in candidate["combination_checks"]] == [
        c["status"] for c in expected_checks
    ]


def test_candidate_combination_evidence_uses_saved_requirement_ids(client, catalog, config):
    data, _ = setup(client, catalog, config, mode="exclude")
    add_target(data, catalog, assign=False)
    data["requirements"][1]["allocations"] = [
        dict(device_id="addon-device", quantity="1", evidence="显式配套角色分配")
    ]
    data["devices"] = [d for d in data["devices"] if d["id"] != "device-1"]
    data["requirements"][0]["device_id"] = None
    candidates = post(
        client,
        "/candidates",
        dict(
            configuration=data,
            requirement_id="r1",
            system="无纸化",
            role="main",
            role_id="main",
            system_definition_id=data["systems"][0]["definition_id"],
            include_all=True,
        ),
    )
    candidate = next(c for c in candidates if c["variant"]["id"] == catalog["variants"][0]["id"])
    check = candidate["combination_checks"][0]
    assert check["status"] == "conflict"
    assert check["groups"][0]["requirement_ids"] == ["r2"]
