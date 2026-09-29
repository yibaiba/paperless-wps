import pytest

from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition

from .conftest import BASE
from .test_evolution_versions import editable
from .test_proposal_generation import apply, draft_for, plan, published, read, write


@pytest.mark.parametrize("scope", ["room", "project"])
def test_setup_inputs_drive_quantity_and_survive_save(client, catalog, project, scope):
    definition, package = published(client, catalog)
    value = editable(SystemDefinition, definition)
    value["roles"][0]["quantity_basis"]["scope"] = scope
    response = client.put(
        BASE + "/definitions/" + definition["id"],
        json=dict(expected_revision=definition["revision"], payload=value),
    )
    assert response.status_code == 200, response.text
    definition = response.json()
    value = editable(KnowledgePackage, package)
    value["definition_revision"] = definition["revision"]
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(expected_revision=package["revision"], payload=value),
    )
    assert response.status_code == 200, response.text
    draft = draft_for(client, definition, response.json())
    before = read(client, draft)["configuration"]
    setup = dict(
        system=before["systems"][0],
        **{scope + "_inputs": [dict(key="seats", kind="quantity", value="3", unit="台")]},
    )
    preview = client.post(
        BASE + "/system-setup-preview", json=dict(configuration=before, setup=setup)
    )
    assert preview.status_code == 200, preview.text
    draft = write(client, draft, [dict(action="system_setup", **setup)])
    actual = read(client, draft)["configuration"]
    assert actual["room_inputs"] == preview.json()["configuration"]["room_inputs"]
    assert actual["project_inputs"] == preview.json()["configuration"]["project_inputs"]
    draft = apply(client, draft, plan(client, draft))
    actual = read(client, draft)["configuration"]
    assert actual["devices"][0]["quantity"] == "3"
    assert actual["systems"][0]["inputs"][0]["value"] == "32"
    saved = client.put(
        BASE + "/projects/" + project["id"], json=dict(expected_revision=0, configuration=actual)
    )
    assert saved.status_code == 200, saved.text
    reopened = client.get(BASE + "/projects/" + project["id"]).json()["configuration"]
    assert reopened["room_inputs"] == actual["room_inputs"]
    assert reopened["project_inputs"] == actual["project_inputs"]
    assert reopened["devices"][0]["quantity"] == "3"
