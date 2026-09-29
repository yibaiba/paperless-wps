from copy import deepcopy

import pytest

from .conftest import AUTHOR
from .test_proposal_generation import apply, plan, read, write
from .test_proposal_prices_and_cycles import priced


def unresolved_draft(client, catalog):
    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    generation = read(client, draft)["configuration"]["generation"]
    generation["sources"] = [
        dict(
            id="understanding",
            object_id="system",
            field="inputs.seats",
            kind="agent_interpretation",
            confirmed=False,
            quote="隔离待核对席位",
        )
    ]
    return write(client, draft, [dict(action="requirements_patch", generation=generation)])


@pytest.mark.parametrize("resolution", ["confirmed", "removed"])
def test_interpretation_persists_through_price_edit_until_explicit_resolution(
    client, catalog, project, resolution
):
    draft = unresolved_draft(client, catalog)
    actual = read(client, draft)
    original = next(c for c in actual["checked"]["checks"] if c["kind"] == "interpretation")
    assert original["category"] == "requirements"
    assert original["action"]["source_id"] == "understanding"
    device = actual["configuration"]["devices"][0]
    draft = write(
        client,
        draft,
        [
            dict(
                action="price_set",
                value=dict(
                    device_id=device["id"],
                    variant_id=device["variant_id"],
                    source_id=device["source_id"],
                    mode="manual",
                    unit_price="0",
                    evidence="隔离零价依据",
                ),
            )
        ],
    )
    actual = read(client, draft)
    issues = [c for c in actual["checked"]["checks"] if c["kind"] == "interpretation"]
    assert len(issues) == 1 and issues[0]["check_id"] == original["check_id"]
    assert not actual["checked"]["readiness"]["ready_for_confirmation"]
    generation = actual["configuration"]["generation"]
    if resolution == "confirmed":
        generation["sources"][0]["confirmed"] = True
    else:
        generation["sources"] = []
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    actual = read(client, draft)
    assert not any(c["kind"] == "interpretation" for c in actual["checked"]["checks"])
    assert actual["checked"]["readiness"]["ready_for_confirmation"]
    url = "/api/configuration/projects/" + project["id"]
    saved = client.put(url, json=dict(expected_revision=0, configuration=actual["configuration"]))
    assert saved.status_code == 200, saved.text
    response = client.post(
        url + "/confirm",
        json=dict(expected_revision=1, fingerprint=saved.json()["fingerprint"], **AUTHOR),
    )
    assert response.status_code == 200, response.text


def test_historical_pass_does_not_hide_interpretation_on_first_confirmation(
    client, catalog, project, monkeypatch
):
    from presales.configuration.projects.calculation import customer_constraints

    draft = unresolved_draft(client, catalog)
    data = read(client, draft)["configuration"]
    url = "/api/configuration/projects/" + project["id"]
    # Reconstruct a pre-fix saved result in the isolated test DB only.
    with monkeypatch.context() as patch:
        patch.setattr(customer_constraints, "interpretation_checks", lambda data: [])
        saved = client.put(url, json=dict(expected_revision=0, configuration=data))
    assert saved.status_code == 200, saved.text
    before = deepcopy(client.get(url).json())
    assert before["readiness"]["ready_for_confirmation"]
    response = client.post(
        url + "/confirm",
        json=dict(expected_revision=1, fingerprint=saved.json()["fingerprint"], **AUTHOR),
    )
    assert response.status_code == 422
    assert client.get(url).json() == before
