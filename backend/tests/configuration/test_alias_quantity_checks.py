import pytest

from presales.configuration.projects.role_allocations import device_ids

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
    identity = device_ids(role)[0]
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


@pytest.mark.parametrize("overrun", ["role", "accessory"])
def test_alias_deduplication_does_not_hide_actual_overallocation(client, catalog, overrun):
    draft = alias_draft(client, catalog, "2")
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    if overrun == "role":
        role = next(r for r in data["requirements"] if r["role_id"] == "server")
        role["allocations"][0]["quantity"] = "3"
    else:
        extra = dict(data["accessory_allocations"][0], id="extra-allocation", quantity="1")
        data["accessory_allocations"].append(extra)
    response = client.post(BASE + "/check", json=dict(configuration=data))
    assert response.status_code == 200, response.text
    kind = "role_allocation" if overrun == "role" else "accessory_allocation"
    assert any(c["kind"] == kind and c["status"] == "conflict" for c in response.json()["checks"])


@pytest.mark.parametrize("confirmed", [True, False])
def test_only_confirmed_linked_aliases_are_excluded_from_role_stock_count(confirmed):
    from presales.configuration.projects.calculation.fulfillment import fulfillment_aliases
    from presales.configuration.projects.calculation.role_allocations import allocation_checks

    data = dict(
        systems=[dict(id="system", definition_id="definition")],
        devices=[dict(id="batch", quantity="2")],
        requirements=[
            dict(id=identity, system_id="system", role_id=role, device_id=device)
            for identity, role, device in [
                ("parent", "terminal", None),
                ("one", "server", "batch"),
                ("two", "server", "batch"),
            ]
        ],
        accessory_allocations=[dict(device_id="batch", demand_id="need", quantity="2")],
    )
    definitions = dict(
        packages=[],
        definitions=[
            dict(
                id="definition",
                roles=[
                    dict(
                        id="server",
                        fulfilled_by=dict(
                            role_id="terminal",
                            need_key="server",
                            status="confirmed" if confirmed else "draft",
                        ),
                    )
                ],
            )
        ],
    )
    demands = [
        dict(id="need", need_key="server", consumer_requirement_ids=["parent"], status="pass")
    ]
    aliases = fulfillment_aliases(data, definitions=definitions, demands=demands)
    checks = allocation_checks(
        data, definitions=definitions, engine=None, fulfilled_ids=set(aliases)
    )
    assert any(c["status"] == "conflict" for c in checks) == (not confirmed)
    data["accessory_allocations"] = []
    aliases = fulfillment_aliases(data, definitions=definitions, demands=demands)
    checks = allocation_checks(
        data, definitions=definitions, engine=None, fulfilled_ids=set(aliases)
    )
    assert any(c["status"] == "conflict" for c in checks)
