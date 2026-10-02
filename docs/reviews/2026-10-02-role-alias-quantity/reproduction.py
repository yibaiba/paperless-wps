import pytest
from presales.configuration.definitions.schemas import KnowledgePackage
from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import BASE
from .test_evolution_versions import editable
from .test_proposal_generation import apply, draft_for, plan, published, read, write


def alias_draft(client, catalog, quantity):
    definition, package = published(client, catalog, accessory=True)
    rule = next(
        r for r in client.get(BASE + "/knowledge").json() if r["kind"] == "accessory"
    )
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
        dict(id=m["id"], revision=response.json()["revision"])
        if m["id"] == rule["id"]
        else m
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
        r
        for r in read(client, draft)["configuration"]["requirements"]
        if r["role_id"] == "server"
    )
    return write(
        client,
        draft,
        [dict(action="requirement_put", value=dict(role, id="second-server-alias"))],
    )


@pytest.mark.parametrize("quantity", ["1", "2"])
def test_aliases_of_one_accessory_need_do_not_double_count_quantity(
    client, catalog, quantity
):
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
    assert len({r["device_id"] for r in roles}) == 1
    device = next(d for d in data["devices"] if d["id"] == roles[0]["device_id"])
    assert device["quantity"] == quantity
    assert len(data["accessory_allocations"]) == 1
    assert data["accessory_allocations"][0]["quantity"] == quantity
