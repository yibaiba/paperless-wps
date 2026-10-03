import pytest

from .test_list_mcp import call, mutation, saved_project
from .test_web_drafts import start, write


@pytest.mark.parametrize("entry", ["web", "mcp"])
def test_clone_is_independent_and_retry_does_not_duplicate(client, catalog, entry):
    draft = start(client, saved_project(client, catalog))
    operations = [dict(action="device_clone", source_device_id="server", new_device_id="clone")]
    request = mutation(draft, operations=operations)
    path = (
        "/api/list-tools/list_update" if entry == "mcp" else f"/api/work-drafts/{draft['id']}/edit"
    )
    response = client.post(path, json=request)
    assert response.status_code == 200, response.text
    assert client.post(path, json=request).json() == response.json()
    current = client.get(f"/api/work-drafts/{draft['id']}").json()
    data = current["configuration"]
    cloned = next(d for d in data["devices"] if d["id"] == "clone")
    assert cloned["quantity"] == "2.5"
    assert cloned["generated_origin"] is None and cloned["origin_suggestion"] is None
    assert all(r["device_id"] != "clone" for r in data["requirements"])
    assert all(a["device_id"] != "clone" for a in data["supply_allocations"])
    assert all(a["device_id"] != "clone" for a in data["accessory_allocations"])
    assert all(a["device_id"] != "clone" for a in data["included_allocations"])
    price = next(p for p in data["quotation"]["prices"] if p["device_id"] == "clone")
    assert price["mode"] == "pending" and price["unit_price"] is None
    assert current["revision"] == draft["revision"] + 1
    assert "clone" in data["drawing_xml"]
    checked = call(client, "list_check", mutation(current))
    saved = call(
        client,
        "list_save",
        mutation(checked, expected_project_revision=1, fingerprint=checked["check_fingerprint"]),
    )
    reopened = client.get("/api/configuration/projects/" + saved["project_id"]).json()
    assert len(reopened["configuration"]["devices"]) == 2


def test_clone_rejects_existing_id_and_foreign_supply_atomically(client, catalog):
    draft = start(client, saved_project(client, catalog))
    for operation in [
        dict(action="device_clone", source_device_id="server", new_device_id="server"),
        dict(
            action="device_clone",
            source_device_id="server",
            new_device_id="clone",
            supply_allocations=[
                dict(id="s", device_id="server", quantity="1", source="purchase", evidence="测试")
            ],
        ),
    ]:
        response = write(client, draft, [operation])
        assert response.status_code == 422, response.text
        assert client.get(f"/api/work-drafts/{draft['id']}").json()["revision"] == draft["revision"]
