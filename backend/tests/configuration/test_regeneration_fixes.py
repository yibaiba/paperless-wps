import pytest

from .test_proposal_generation import apply, plan, read, write
from .test_proposal_prices_and_cycles import priced
from .test_role_partial_reuse import existing_draft


@pytest.mark.parametrize("seats", ["32", "48", "0"])
def test_split_role_regeneration_preserves_manually_locked_variant(client, catalog, seats):
    draft = existing_draft(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    original = next(d for d in data["devices"] if d.get("generated_origin"))
    replacement = {
        k: v
        for k, v in original.items()
        if k not in {"generated_origin", "variant_snapshot", "source_snapshot", "origin_suggestion"}
    }
    replacement.update(
        variant_id=catalog["variants"][1]["id"], source_id=catalog["sources"][1]["id"]
    )
    generation = data["generation"]
    generation["preferences"][0]["required_variant_id"] = ""
    draft = write(
        client,
        draft,
        [
            dict(action="device_put", value=replacement),
            dict(action="requirements_patch", generation=generation),
        ],
    )
    before = read(client, draft)["configuration"]
    locked = next(d for d in before["devices"] if d["id"] == original["id"])
    assert locked["generated_origin"]["variant_locked"]
    assert (
        before["requirements"][0]["device_id"] is None
        and len(before["requirements"][0]["allocations"]) == 2
    )
    from .test_proposal_evolution import change_seats

    draft = change_seats(client, draft, seats)
    proposed = plan(client, draft)
    draft = apply(client, draft, proposed)
    after = read(client, draft)["configuration"]
    actual = next(d for d in after["devices"] if d["id"] == original["id"])
    assert after["requirements"][0]["allocations"] == before["requirements"][0]["allocations"]
    if seats != "32":
        assert proposed["option"]["status"] == "conflict"
    assert actual["variant_id"] == locked["variant_id"], (
        "Regeneration must not rewrite a manually locked split-role device"
    )


def test_regeneration_preserves_explicit_unknown_supply(client, catalog):
    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    device = data["devices"][0]
    allocations = [
        dict(
            id=kind,
            device_id=device["id"],
            quantity="16",
            source=kind,
            evidence="隔离人工确认：另一半供货待确认",
        )
        for kind in ("purchase", "unknown")
    ]
    draft = write(
        client, draft, [dict(action="supply_set", device_id=device["id"], allocations=allocations)]
    )
    before = read(client, draft)["checked"]
    assert before["quotation_output"]["total"] is None
    assert before["project_output"]["procurement_lines"][0]["quantity"] == "16"
    proposed = plan(client, draft)
    draft = apply(client, draft, proposed)
    after = read(client, draft)["checked"]
    assert (
        after["configuration"]["supply_allocations"]
        == before["configuration"]["supply_allocations"]
    ), "Regeneration must not turn explicitly unknown supply into purchase"


def test_revision_comparison_reports_changed_room_quantity_input(client, catalog, project):
    from copy import deepcopy

    from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition

    from .conftest import post
    from .test_evolution_versions import editable
    from .test_proposal_generation import draft_for, published

    definition, package = published(client, catalog)
    payload = editable(SystemDefinition, definition)
    payload["roles"][0]["quantity_basis"]["scope"] = "room"
    response = client.put(
        "/api/configuration/definitions/" + definition["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert response.status_code == 200, response.text
    definition = response.json()
    payload = editable(KnowledgePackage, package)
    payload["definition_revision"] = definition["revision"]
    response = client.put(
        "/api/configuration/knowledge-packages/" + package["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert response.status_code == 200, response.text
    package = response.json()
    draft = draft_for(client, definition, package)
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                room_inputs={"room": [dict(key="seats", kind="quantity", value="32", unit="台")]},
            )
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    url = "/api/configuration/projects/" + project["id"]
    first = client.put(url, json=dict(expected_revision=0, configuration=data))
    assert first.status_code == 200, first.text
    data = deepcopy(first.json()["configuration"])
    data["room_inputs"]["room"][0]["value"] = "48"
    second = client.put(url, json=dict(expected_revision=1, configuration=data))
    assert second.status_code == 200, second.text
    actual = second.json()
    assert any(
        c["kind"] == "role_allocation" and c["status"] == "conflict" for c in actual["checks"]
    )
    compared = post(
        client, "/projects/" + project["id"] + "/compare", dict(base_revision=1, target_revision=2)
    )
    assert any(c["kind"] == "room_inputs" for c in compared["changes"]), (
        "Room-level scale changed from 32 to 48 and must appear in the saved revision diff"
    )


def test_manual_supply_survives_increase_and_decrease(client, catalog):
    from .test_proposal_evolution import change_seats

    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    device = read(client, draft)["configuration"]["devices"][0]
    allocations = [
        dict(
            id=source,
            device_id=device["id"],
            source=source,
            quantity="16",
            evidence="隔离人工供货安排",
        )
        for source in ("purchase", "unknown")
    ]
    draft = write(
        client, draft, [dict(action="supply_set", device_id=device["id"], allocations=allocations)]
    )
    for quantity, status in [("48", "unknown"), ("16", "conflict")]:
        draft = change_seats(client, draft, quantity)
        draft = apply(client, draft, plan(client, draft))
        checked = read(client, draft)["checked"]
        assert checked["configuration"]["supply_allocations"] == allocations
        assert checked["configuration"]["devices"][0]["quantity"] == quantity
        assert next(c for c in checked["checks"] if c["kind"] == "supply")["status"] == status
        assert checked["quotation_output"]["total"] is None


def test_project_inputs_and_customer_constraints_appear_in_revision_diff(client, catalog, project):
    from copy import deepcopy

    from .conftest import post

    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    url = "/api/configuration/projects/" + project["id"]
    first = client.put(
        url, json=dict(expected_revision=0, configuration=read(client, draft)["configuration"])
    )
    assert first.status_code == 200, first.text
    before = first.json()["configuration"]
    after = deepcopy(before)
    after["project_inputs"] = [dict(key="seats", kind="quantity", value="48", unit="台")]
    after["generation"].update(budget="400", budget_evidence="隔离新增预算")
    second = client.put(url, json=dict(expected_revision=1, configuration=after))
    assert second.status_code == 200, second.text
    compared = post(
        client, "/projects/" + project["id"] + "/compare", dict(base_revision=1, target_revision=2)
    )
    by_kind = {c["kind"]: c for c in compared["changes"]}
    assert by_kind["project_inputs"]["before"] == []
    assert by_kind["project_inputs"]["after"] == after["project_inputs"]
    assert by_kind["generation"]["before"] == before["generation"]
    assert by_kind["generation"]["after"] == after["generation"]
