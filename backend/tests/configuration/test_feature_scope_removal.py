from copy import deepcopy

from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition

from .conftest import AUTHOR, BASE
from .test_catalog_updates import COLUMN, publish
from .test_evolution_versions import editable
from .test_proposal_evolution import change_seats
from .test_proposal_generation import apply, call, draft_for, plan, published, read, write
from .test_proposal_prices_and_cycles import priced


def revise_definition(client, catalog, *, optional=False, room_fixed=False):
    definition, package = published(client, catalog)
    value = editable(SystemDefinition, definition)
    if optional:
        role = deepcopy(value["roles"][0])
        role.update(id="vote", name="投票功能", feature="投票")
        value["roles"].append(role)
    if room_fixed:
        value["roles"][0]["quantity_basis"].update(
            scope="room", mode="per_group", factor="1", input_key="", input_unit=""
        )
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
    for variant in catalog["variants"]:
        publish(client, variant, amount="10")
    draft = draft_for(client, definition, response.json())
    draft = write(
        client,
        draft,
        [
            dict(
                action="quotation_set",
                value=dict(price_column=COLUMN, price_adoption_date="2026-09-29"),
            )
        ],
    )
    return draft


def test_unknown_feature_choice_cannot_confirm_after_apply(client, catalog, project):
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
    proposal = plan(client, draft)
    questions = call(
        client,
        "list_get",
        dict(
            draft_id=draft["id"],
            proposal_id=proposal["proposal_id"],
            option_id=proposal["option"]["id"],
            view="proposal_questions",
        ),
    )
    assert any(q["code"] == "features_unknown" for q in questions["items"])
    draft = apply(client, draft, proposal)
    actual = read(client, draft)
    assert "system" not in actual["configuration"]["generation"]["features_confirmed"]
    url = "/api/configuration/projects/" + project["id"]
    saved = client.put(url, json=dict(expected_revision=0, configuration=actual["configuration"]))
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        url + "/confirm",
        json=dict(expected_revision=1, fingerprint=saved.json()["fingerprint"], **AUTHOR),
    )
    assert confirmed.status_code == 422, (
        f"Unconfirmed choices allowed confirmation: {confirmed.status_code}"
    )


def test_proposal_removal_cleans_reuse_references(client, catalog):
    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    device = data["devices"][0]
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                requirement_id=data["requirements"][0]["id"],
                reusable_device_ids=[device["id"]],
                evidence="隔离允许复用当前设备",
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    draft = change_seats(client, draft, "0")
    proposal = plan(client, draft)
    assert device["id"] in proposal["option"]["removal_candidates"]
    draft = write(
        client,
        draft,
        [
            dict(
                action="proposal_apply",
                proposal_id=proposal["proposal_id"],
                option_id=proposal["option"]["id"],
                fingerprint=proposal["fingerprint"],
                remove_device_ids=[device["id"]],
            )
        ],
    )
    data = read(client, draft)["configuration"]
    assert not data["devices"]
    response = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="change-room-name",
            operations=[
                dict(action="requirements_patch", rooms=[dict(id="room", name="隔离会议室改名")])
            ],
        ),
    )
    assert response.status_code == 200, (
        f"Next requirement edit fails after removal: {response.text}"
    )


def test_room_fixed_quantity_requires_room_scope(client, catalog):
    draft = revise_definition(client, catalog, room_fixed=True)
    data = read(client, draft)["configuration"]
    system = dict(data["systems"][0], room_id=None)
    draft = write(
        client,
        draft,
        [dict(action="requirements_patch", systems=[dict(system=system, features_confirmed=True)])],
    )
    proposal = plan(client, draft)
    questions = call(
        client,
        "list_get",
        dict(
            draft_id=draft["id"],
            proposal_id=proposal["proposal_id"],
            option_id=proposal["option"]["id"],
            view="proposal_questions",
        ),
    )
    assert any(
        q["code"] == "quantity_scope_missing" and q["recipient"] == "customer"
        for q in questions["items"]
    )
    draft = apply(client, draft, proposal)
    actual = read(client, draft)
    assert actual["configuration"]["systems"][0]["room_id"] is None
    assert actual["configuration"]["devices"] == []
    assert not actual["checked"]["readiness"]["ready_for_confirmation"]
