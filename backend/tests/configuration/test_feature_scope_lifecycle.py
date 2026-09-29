from copy import deepcopy

import pytest
import zen

from presales.configuration.definitions.schemas import SystemDefinition
from presales.configuration.projects.planning.quantities import role_quantity
from presales.rules.engine import ZenQuantityEngine

from .conftest import AUTHOR, BASE
from .test_evolution_versions import editable
from .test_feature_scope_removal import revise_definition
from .test_proposal_generation import apply, plan, read, write


def pending_features(client, catalog):
    draft = revise_definition(client, catalog, optional=True)
    data = read(client, draft)["configuration"]
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                systems=[dict(system=data["systems"][0], features_confirmed=False)],
            )
        ],
    )
    return apply(client, draft, plan(client, draft))


def test_feature_issue_survives_price_edit_and_web_setup_resolves_it(client, catalog):
    draft = pending_features(client, catalog)
    actual = read(client, draft)
    issue = next(c for c in actual["checked"]["checks"] if c["kind"] == "feature_selection")
    assert issue["category"] == "requirements"
    assert issue["action"]["missing_fields"] == ["features", "features_confirmed"]
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
    assert any(c.get("check_id") == issue["check_id"] for c in actual["checked"]["checks"])
    assert not actual["checked"]["readiness"]["ready_for_confirmation"]
    system = actual["configuration"]["systems"][0]
    preview = client.post(
        BASE + "/system-setup-preview",
        json=dict(
            configuration=actual["configuration"],
            setup=dict(system=system, features_confirmed=True),
        ),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["configuration"]["generation"]["features_confirmed"] == ["system"]
    draft = write(
        client, draft, [dict(action="system_setup", system=system, features_confirmed=True)]
    )
    actual = read(client, draft)
    assert actual["checked"]["readiness"]["ready_for_confirmation"]
    assert actual["configuration"]["systems"][0]["features"] == []
    draft = write(
        client, draft, [dict(action="system_setup", system=system, features_confirmed=False)]
    )
    assert not read(client, draft)["checked"]["readiness"]["ready_for_confirmation"]


def test_feature_check_uses_pinned_definition(client, catalog):
    draft = pending_features(client, catalog)
    data = read(client, draft)["configuration"]
    system = data["systems"][0]
    definition = next(
        d
        for d in client.get(BASE + "/definitions").json()["definitions"]
        if d["id"] == system["definition_id"]
    )
    payload = editable(SystemDefinition, definition)
    payload["roles"] = [r for r in payload["roles"] if not r["feature"]]
    result = client.put(
        BASE + "/definitions/" + definition["id"],
        json=dict(expected_revision=definition["revision"], payload=payload),
    )
    assert result.status_code == 200, result.text
    checked = client.post(BASE + "/check", json=dict(configuration=data))
    assert checked.status_code == 200, checked.text
    issue = next(c for c in checked.json()["checks"] if c["kind"] == "feature_selection")
    assert issue["evidence"][0]["definition_revision"] == definition["revision"]


def test_historical_feature_pass_cannot_first_confirm(client, catalog, project, monkeypatch):
    from presales.configuration.projects.calculation import evaluate

    draft = pending_features(client, catalog)
    data = read(client, draft)["configuration"]
    url = BASE + "/projects/" + project["id"]
    # Reconstruct the pre-fix stored result only in the isolated test database.
    with monkeypatch.context() as patch:
        patch.setattr(evaluate, "feature_checks", lambda data, definitions: [])
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


def test_selected_room_quantity_becomes_unknown_and_recovers(client, catalog):
    draft = revise_definition(client, catalog, room_fixed=True)
    draft = apply(client, draft, plan(client, draft))
    before = read(client, draft)["configuration"]
    assert before["devices"][0]["quantity"] == "1"
    draft = write(
        client, draft, [dict(action="system_put", value=dict(before["systems"][0], room_id=None))]
    )
    actual = read(client, draft)
    check = next(c for c in actual["checked"]["checks"] if c["kind"] == "role_allocation")
    assert check["status"] == "unknown"
    assert check["action"]["missing_fields"] == ["room_id"]
    assert actual["configuration"]["devices"] == before["devices"]
    draft = write(client, draft, [dict(action="system_put", value=before["systems"][0])])
    assert read(client, draft)["checked"]["readiness"]["ready_for_confirmation"]


@pytest.mark.parametrize("scope", ["room", "system", "project"])
@pytest.mark.parametrize("mode", ["per_group", "per_unit", "per_capacity"])
def test_quantity_scope_is_required_only_for_room(scope, mode):
    basis = dict(
        status="confirmed", scope=scope, mode=mode, factor="1", input_key="seats", input_unit="台"
    )
    inputs = [dict(key="seats", value="2", unit="台")]
    system = dict(id="s", room_id=None, inputs=inputs)
    data = dict(rooms=[], project_inputs=inputs, room_inputs={})
    quantity, gap, _ = role_quantity(
        dict(id="r", quantity_basis=basis),
        system,
        configuration=data,
        engine=ZenQuantityEngine(zen.ZenEngine()),
    )
    if scope == "room":
        assert quantity is None and gap["code"] == "quantity_scope_missing"
    else:
        assert gap is None and quantity == (1 if mode == "per_group" else 2)


def test_historical_room_scope_pass_cannot_first_confirm(client, catalog, project, monkeypatch):
    from presales.configuration.projects.planning import quantities

    draft = revise_definition(client, catalog, room_fixed=True)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    data["systems"][0]["room_id"] = None
    url = BASE + "/projects/" + project["id"]
    # This isolated saved result models the previous fixed-quantity scope bug.
    with monkeypatch.context() as patch:
        patch.setattr(quantities, "scope_gap", lambda *args: None)
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
