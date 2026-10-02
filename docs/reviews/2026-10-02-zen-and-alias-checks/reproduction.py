import pytest

from .conftest import BASE
from .test_fulfilled_role_quantity_review import alias_draft
from .test_proposal_generation import apply, plan, read, write


@pytest.mark.parametrize("quantity", ["1", "2"])
def test_fulfilled_role_aliases_do_not_reserve_same_accessory_twice(client, catalog, quantity):
    draft = alias_draft(client, catalog, quantity)
    draft = write(
        client, draft, [dict(action="remove", collection="requirements", id="second-server-alias")]
    )
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    role = next(r for r in data["requirements"] if r["role_id"] == "server")
    identity = role["device_id"]
    role.update(
        device_id=None,
        allocations=[
            dict(device_id=identity, quantity=quantity, evidence="隔离已确认配套的角色引用")
        ],
    )
    data["requirements"].append(dict(role, id="second-alias"))
    response = client.post(BASE + "/check", json=dict(configuration=data))
    assert response.status_code == 200, response.text
    checked = response.json()
    assert len(checked["configuration"]["accessory_allocations"]) == 1
    assert not any(
        c["kind"] == "accessory_allocation" and c["status"] == "conflict" for c in checked["checks"]
    )
    duplicates = [
        c
        for c in checked["checks"]
        if c["kind"] == "role_allocation"
        and c.get("device_id") == identity
        and c["status"] == "conflict"
    ]
    assert not duplicates, duplicates
