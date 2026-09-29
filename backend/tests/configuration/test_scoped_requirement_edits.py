from copy import deepcopy

from .conftest import BASE
from .test_proposal_generation import read, write
from .test_proposal_prices_and_cycles import priced


def test_deleting_room_clears_only_its_inputs(client, catalog):
    draft = priced(client, catalog, amount="10")
    inputs = [dict(key="seats", kind="quantity", value="32", unit="台")]
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                rooms=[dict(id="other", name="其他房间")],
                room_inputs={"room": inputs, "other": inputs},
                project_inputs=inputs,
            )
        ],
    )
    response = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="delete-room",
            operations=[dict(action="remove", collection="rooms", id="room")],
        ),
    )
    assert response.status_code == 200, response.text
    data = read(client, response.json())["configuration"]
    assert data["room_inputs"] == {"other": inputs}
    assert data["project_inputs"] == inputs
    assert data["systems"][0]["room_id"] is None


def test_role_resource_patch_must_not_overwrite_multiple_requirements(client, catalog):
    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    first = data["requirements"][0]
    second = dict(
        first, id="another-terminal", resources=[dict(key="memory", amount="8", unit="GB")]
    )
    draft = write(client, draft, [dict(action="requirement_put", value=second)])
    before = deepcopy(read(client, draft))
    response = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="ambiguous-resource",
            operations=[
                dict(
                    action="requirements_patch",
                    systems=[
                        dict(
                            system=data["systems"][0],
                            features_confirmed=True,
                            roles=[
                                dict(
                                    role_id=first["role_id"],
                                    resources=[dict(key="memory", amount="16", unit="GB")],
                                )
                            ],
                        )
                    ],
                )
            ],
        ),
    )
    assert response.status_code == 422, response.text
    assert read(client, draft) == before


def test_setup_preserves_room_and_project_input_scopes(client, catalog):
    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    room_inputs = [dict(key="room_count", kind="quantity", value="3", unit="台")]
    project_inputs = [dict(key="project_count", kind="quantity", value="4", unit="台")]
    setup = dict(system=data["systems"][0], room_inputs=room_inputs, project_inputs=project_inputs)
    response = client.post(
        BASE + "/system-setup-preview", json=dict(configuration=data, setup=setup)
    )
    assert response.status_code == 200, response.text
    draft = write(client, draft, [dict(action="system_setup", **setup)])
    actual = read(client, draft)["configuration"]
    assert actual["room_inputs"]["room"] == room_inputs
    assert actual["project_inputs"] == project_inputs
    assert actual["requirements"] == data["requirements"]


def test_room_deletion_retry_and_checkpoint_restore(client, catalog):
    draft = priced(client, catalog, amount="10")
    inputs = [dict(key="seats", kind="quantity", value="32", unit="台")]
    draft = write(client, draft, [dict(action="requirements_patch", room_inputs={"room": inputs})])
    before = read(client, draft)["configuration"]
    request = dict(
        draft_id=draft["id"],
        expected_revision=draft["revision"],
        operation_id="delete-once",
        operations=[dict(action="remove", collection="rooms", id="room")],
    )
    first = client.post("/api/list-tools/list_update", json=request)
    assert first.status_code == 200, first.text
    assert client.post("/api/list-tools/list_update", json=request).json() == first.json()
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=first.json()["revision"],
            operation_id="undo-delete",
            checkpoint_revision=draft["revision"],
        ),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["configuration"] == before


def test_single_resource_edit_and_explicit_id_edit_preserve_other_requirements(client, catalog):
    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    first = data["requirements"][0]
    resources = [dict(key="memory", amount="16", unit="GB")]
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                systems=[
                    dict(
                        system=data["systems"][0],
                        features_confirmed=True,
                        roles=[dict(role_id=first["role_id"], resources=resources)],
                    )
                ],
            )
        ],
    )
    first = read(client, draft)["configuration"]["requirements"][0]
    assert first["resources"][0]["amount"] == "16"
    second = dict(first, id="second")
    draft = write(client, draft, [dict(action="requirement_put", value=second)])
    draft = write(client, draft, [dict(action="requirement_put", value=dict(first, resources=[]))])
    actual = {r["id"]: r for r in read(client, draft)["configuration"]["requirements"]}
    assert actual[first["id"]]["resources"] == []
    assert actual["second"]["resources"] == first["resources"]


def test_scope_setup_missing_room_is_atomic_and_omitted_values_are_preserved(client, catalog):
    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    inputs = [dict(key="seats", kind="quantity", value="3", unit="台")]
    draft = write(
        client,
        draft,
        [dict(action="requirements_patch", room_inputs={"room": inputs}, project_inputs=inputs)],
    )
    before = read(client, draft)
    response = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="invalid-room",
            operations=[
                dict(
                    action="system_setup",
                    system=dict(data["systems"][0], room_id=None),
                    room_inputs=inputs,
                    project_inputs=[],
                )
            ],
        ),
    )
    assert response.status_code == 422
    assert read(client, draft) == before
    draft = write(
        client, draft, [dict(action="system_setup", system=data["systems"][0], project_inputs=[])]
    )
    actual = read(client, draft)["configuration"]
    assert actual["room_inputs"] == {"room": inputs}
    assert actual["project_inputs"] == []
