import pytest

from presales.configuration.definitions.schemas import KnowledgePackage
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.projects.role_allocations import device_ids

from .conftest import BASE
from .test_evolution_versions import editable
from .test_proposal_generation import apply, draft_for, plan, published, read, write


def alias_draft(client, catalog, quantity):
    definition, package = published(client, catalog, accessory=True)
    rule = next(r for r in client.get(BASE + "/knowledge").json() if r["kind"] == "accessory")
    payload = editable(KnowledgeInput, rule)
    payload.update(
        factor=quantity,
        allocation_mode="consumable",
        quantity_evidence="隔离固定配套数量",
    )
    response = client.put(
        BASE + "/knowledge/" + rule["id"],
        json=dict(
            expected_revision=rule["revision"],
            payload=payload,
        ),
    )
    assert response.status_code == 200, response.text
    payload = editable(KnowledgePackage, package)
    payload["members"] = [
        dict(id=m["id"], revision=response.json()["revision"]) if m["id"] == rule["id"] else m
        for m in payload["members"]
    ]
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(
            expected_revision=package["revision"],
            payload=payload,
        ),
    )
    assert response.status_code == 200, response.text
    draft = draft_for(client, definition, response.json())
    role = next(
        r for r in read(client, draft)["configuration"]["requirements"] if r["role_id"] == "server"
    )
    return write(
        client,
        draft,
        [dict(action="requirement_put", value=dict(role, id="second-server-alias"))],
    )


@pytest.mark.parametrize("quantity", ["1", "2"])
def test_aliases_of_one_accessory_need_do_not_double_count_quantity(client, catalog, quantity):
    draft = alias_draft(client, catalog, quantity)
    proposal = plan(client, draft)
    draft = apply(client, draft, proposal)
    result = read(client, draft)
    assert not any(
        c["kind"] == "role_allocation" and c["status"] == "conflict"
        for c in result["checked"]["checks"]
    )
    data = result["configuration"]
    roles = [r for r in data["requirements"] if r["role_id"] == "server"]
    assert len(roles) == 2
    assert len({i for r in roles for i in device_ids(r)}) == 1
    device = next(d for d in data["devices"] if d["id"] == device_ids(roles[0])[0])
    assert device["quantity"] == quantity
    assert len(data["accessory_allocations"]) == 1
    assert data["accessory_allocations"][0]["quantity"] == quantity


def test_batch_alias_regenerate_restore_and_saved_reopen(client, catalog, project):
    from .conftest import AUTHOR
    from .test_proposal_generation import call

    draft = alias_draft(client, catalog, "2")
    checkpoint = draft["revision"]
    draft = apply(client, draft, plan(client, draft))
    initial = read(client, draft)["configuration"]
    draft = apply(client, draft, plan(client, draft))
    repeated = read(client, draft)["configuration"]
    assert repeated["requirements"] == initial["requirements"]
    assert repeated["accessory_allocations"] == initial["accessory_allocations"]
    assert {d["id"] for d in repeated["devices"]} == {d["id"] for d in initial["devices"]}
    response = client.put(
        BASE + "/projects/" + project["id"], json=dict(expected_revision=0, configuration=repeated)
    )
    assert response.status_code == 200, response.text
    reopened = call(
        client,
        "list_create",
        dict(
            project_id=project["id"],
            revision=1,
            name="隔离批量角色重开",
            operation_id="alias-reopen",
            **AUTHOR,
        ),
    )
    reopened = apply(client, reopened, plan(client, reopened))
    actual = read(client, reopened)["configuration"]
    assert actual["requirements"] == initial["requirements"]
    assert actual["accessory_allocations"] == initial["accessory_allocations"]
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            checkpoint_revision=checkpoint,
            operation_id="alias-undo",
        ),
    )
    assert restored.status_code == 200, restored.text
    assert not restored.json()["configuration"]["devices"]
    regenerated = apply(client, restored.json(), plan(client, restored.json()))
    assert read(client, regenerated)["configuration"]["requirements"] == initial["requirements"]


@pytest.mark.parametrize("mode,expected", [("consumable", "3"), ("shareable", "2")])
def test_batch_alias_references_allocated_quantity_not_entire_stock(mode, expected):
    from copy import deepcopy

    from presales.configuration.projects.planning.fulfillment import bind_fulfilled_device

    task = dict(
        requirement=dict(id="alias"),
        system=dict(id="system"),
        role=dict(fulfilled_by=dict(role_id="parent", need_key="server")),
    )
    data = dict(
        devices=[dict(id="stock", quantity="5")],
        requirements=[
            dict(id="parent", system_id="system", role_id="parent"),
            dict(id="alias", system_id="system", role_id="server", device_id=None, allocations=[]),
        ],
        accessory_allocations=[
            dict(demand_id=identity, device_id="stock", quantity=quantity)
            for identity, quantity in [("a", "2"), ("b", "1"), ("unrelated", "1")]
        ],
    )
    demands = [
        dict(
            id=identity,
            need_key="server" if identity != "unrelated" else "other",
            consumer_requirement_ids=["parent"],
            rule=dict(allocation_mode=mode),
        )
        for identity in ["a", "b", "unrelated"]
    ]
    before = deepcopy(data)
    actual = bind_fulfilled_device(data, task=task, identity="stock", demands=demands)
    alias = next(r for r in actual["requirements"] if r["id"] == "alias")
    assert alias["device_id"] is None
    assert alias["allocations"][0]["quantity"] == expected
    assert actual["devices"] == before["devices"]
    assert data == before


def test_manual_batch_alias_quantity_is_not_overwritten(client, catalog):
    draft = alias_draft(client, catalog, "2")
    draft = apply(client, draft, plan(client, draft))
    role = next(
        r for r in read(client, draft)["configuration"]["requirements"] if r["role_id"] == "server"
    )
    role["allocations"][0]["quantity"] = "1"
    role["allocations"][0]["evidence"] = "隔离人工明确部分引用"
    draft = write(client, draft, [dict(action="requirement_put", value=role)])
    draft = apply(client, draft, plan(client, draft))
    actual = next(
        r for r in read(client, draft)["configuration"]["requirements"] if r["id"] == role["id"]
    )
    assert actual == role
