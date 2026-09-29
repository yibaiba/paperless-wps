import pytest

from .test_proposal_generation import apply, draft_for, plan, published, read, write


def reusable_draft(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    data = read(client, draft)["configuration"]
    variant, source = catalog["variants"][0], catalog["sources"][0]
    devices = [
        dict(
            id=identity,
            name=identity,
            variant_id=variant["id"],
            source_id=source["id"],
            quantity="32",
            kind="hardware",
        )
        for identity in ("existing-a", "existing-b")
    ]
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                requirement_id=data["requirements"][0]["id"],
                required_variant_id=variant["id"],
                reusable_device_ids=[device["id"] for device in devices],
                evidence="隔离客户确认允许复用任一现有设备",
            )
        ],
    )
    return write(
        client,
        draft,
        [
            *[dict(action="device_put", value=device) for device in devices],
            dict(action="requirements_patch", generation=generation),
        ],
    )


def test_alternative_reuse_has_unique_identity_and_applies_selected_device(client, catalog):
    draft = reusable_draft(client, catalog)
    first = plan(client, draft)
    second = plan(client, draft, proposal_id=first["proposal_id"], option_offset=1)
    assert first["option"]["id"] != second["option"]["id"]
    applied = apply(client, draft, second)
    data = read(client, applied)["configuration"]
    assert data["requirements"][0]["device_id"] == "existing-b"
    assert len(data["devices"]) == 2


@pytest.mark.parametrize("collection", ["requirements", "systems"])
def test_remove_requirement_owner_cleans_generation_preferences(client, catalog, collection):
    draft = reusable_draft(client, catalog)
    data = read(client, draft)["configuration"]
    draft = write(
        client, draft, [dict(action="remove", collection=collection, id=data[collection][0]["id"])]
    )
    assert read(client, draft)["configuration"]["generation"]["preferences"] == []
    assert plan(client, draft)["proposal_id"]


def test_remove_reusable_device_preserves_other_preferences_and_allows_requirements_edit(
    client, catalog
):
    draft = reusable_draft(client, catalog)
    draft = write(client, draft, [dict(action="remove", collection="devices", id="existing-a")])
    generation = read(client, draft)["configuration"]["generation"]
    assert generation["preferences"][0]["reusable_device_ids"] == ["existing-b"]
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    applied = apply(client, draft, plan(client, draft))
    assert read(client, applied)["configuration"]["requirements"][0]["device_id"] == "existing-b"


@pytest.mark.parametrize(
    "scope,field,changes",
    [
        ("project", "generation.budget", {"budget": "1", "budget_evidence": "隔离待确认预算"}),
        (
            "room",
            "inputs.seats",
            {
                "room_inputs": {
                    "room": [{"key": "seats", "kind": "quantity", "value": "48", "unit": "台"}]
                }
            },
        ),
        (
            "project",
            "project_inputs.seats",
            {"project_inputs": [{"key": "seats", "kind": "quantity", "value": "48", "unit": "台"}]},
        ),
    ],
)
def test_unconfirmed_room_and_project_values_cannot_change_effective_requirements(
    client, catalog, scope, field, changes
):
    from uuid import uuid4

    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    original = read(client, draft)["configuration"]
    generation = dict(
        original["generation"],
        sources=[
            dict(
                id="guess",
                object_id=scope,
                field=field,
                kind="agent_interpretation",
                confirmed=False,
                quote="隔离待确认理解",
            )
        ],
    )
    operation = dict(action="requirements_patch", generation=generation)
    if "budget" in changes:
        generation.update(changes)
    else:
        operation.update(changes)
    response = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            operations=[operation],
        ),
    )
    assert response.status_code == 422, response.text
    assert read(client, draft)["configuration"] == original
    generation["sources"][0]["confirmed"] = True
    assert write(client, draft, [operation])["revision"] > draft["revision"]
