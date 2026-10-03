from copy import deepcopy
from uuid import uuid4

import pytest

from presales.configuration.projects.planning.dependency_scope import DependencyScope
from presales.configuration.projects.repository import ProjectConfigurations
from presales.configuration.projects.schemas import Configuration
from presales.rules.calculation import digest

from .test_wps_next_edits import accept, completion_body, preview, sync_body


def seed_unrelated_systems(client, headers, body, count):
    bound = client.get(f"/api/wps/bindings/{body['binding_id']}", headers=headers).json()
    original = body["business_operations"][0]["system"]
    operations = deepcopy(body["business_operations"])
    for number in range(count):
        room = f"unrelated-room-{number}"
        operations.extend(
            [
                dict(action="room_put", value=dict(id=room, name="无关房间")),
                dict(
                    action="system_put",
                    value=dict(original, id=f"unrelated-{number}", room_id=room),
                ),
            ]
        )
    response = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=bound["draft_id"],
            expected_revision=body["expected_draft_revision"],
            operation_id=str(uuid4()),
            operations=operations,
        ),
    )
    assert response.status_code == 200, response.text
    body.update(expected_draft_revision=response.json()["revision"], business_operations=[])


def test_http_preview_checks_only_dependency_closure_but_sync_checks_all(
    client, catalog, monkeypatch
):
    headers, body = completion_body(client, catalog, accessory=False)
    seed_unrelated_systems(client, headers, body, 1000)
    observed = []
    original = ProjectConfigurations._check

    def record(self, data, **kwargs):
        observed.append(len(data.systems))
        return original(self, data, **kwargs)

    monkeypatch.setattr(ProjectConfigurations, "_check", record)
    result = preview(client, headers, body)
    assert result["items"]
    assert result["evaluation_scope"]["system"] == ["system"]
    assert observed and set(observed) == {1}
    assert len(result["configuration"]["systems"]) == 1001
    observed.clear()
    accepted = accept(body, result["items"][0])
    response = client.post("/api/wps/sync/preview", headers=headers, json=sync_body(accepted))
    assert response.status_code == 200, response.text
    assert observed and set(observed) == {1001}


@pytest.mark.parametrize("shared", [False, True])
def test_scoped_checks_and_demands_equal_full_engine_for_affected_system(client, catalog, shared):
    headers, body = completion_body(client, catalog)
    seed_unrelated_systems(client, headers, body, 8)
    first = preview(client, headers, body)["items"][0]
    body = accept(body, first)
    projected = preview(client, headers, body)["configuration"]
    if shared:
        projected["devices"][0]["quantity"] = "1"
        for allocation in projected["supply_allocations"]:
            allocation["quantity"] = "1"
        projected["requirements"].append(
            dict(projected["requirements"][0], id="shared-role", system_id="unrelated-0")
        )
    with client.app.state.session_factory() as session:
        repository = ProjectConfigurations(session, client.app.state.quantity_engine)
        data = Configuration.model_validate(projected)
        full = repository.check(data)
        scoped = repository.scoped(DependencyScope("system")).check(data)
    assert scoped["suggestions"] == full["suggestions"]
    included = set(scoped["evaluation_scope"]["system"])
    excluded = {s["id"] for s in projected["systems"]} - included
    expected = [c for c in full["checks"] if c.get("system_id") not in excluded]
    assert scoped["checks"] == expected
    assert scoped["configuration"]["drawing_xml"] == projected["drawing_xml"]
    assert scoped["configuration"] == dict(
        full["configuration"], drawing_xml=projected["drawing_xml"]
    )
    assert included == ({"system", "unrelated-0"} if shared else {"system"})


def dependency_data():
    return dict(
        systems=[
            dict(id=s, room_id="room" if s != "outside" else "other", knowledge_package_id="p")
            for s in ("a", "b", "outside")
        ],
        requirements=[
            dict(id=f"r-{s}", system_id=s, device_id=f"d-{s}") for s in ("a", "b", "outside")
        ],
        devices=[dict(id=f"d-{s}") for s in ("a", "b", "outside")],
        accessory_allocations=[],
        included_allocations=[],
        accessory_choices=[],
    )


def test_dependency_closure_keeps_shared_supply_and_cross_room_allocations():
    data = dependency_data()
    data["requirements"][1]["device_id"] = "d-a"
    assert DependencyScope("a").closure(data, [])["system"] == {"a", "b"}
    rule = dict(
        id="accessory", revision=1, kind="accessory", status="confirmed", calculation_scope="system"
    )
    data["accessory_allocations"] = [
        dict(device_id="d-a", demand_id=digest(["accessory", "system", "outside"]))
    ]
    assert DependencyScope("a").closure(data, [rule])["system"] == {"a", "b", "outside"}


def test_dependency_closure_keeps_room_and_project_combination_targets():
    data = dependency_data()
    rule = dict(
        id="combo",
        revision=1,
        kind="combination",
        status="confirmed",
        combination=dict(scope="room"),
    )
    assert DependencyScope("a").closure(data, [rule])["system"] == {"a", "b"}
    rule["combination"]["scope"] = "project"
    assert DependencyScope("a").closure(data, [rule])["system"] == {"a", "b", "outside"}


def test_explicit_room_and_allocation_edits_are_scope_roots():
    data = dependency_data()
    assert DependencyScope("a", frozenset({"other"})).closure(data, [])["system"] == {
        "a",
        "outside",
    }
    data["accessory_allocations"] = [dict(id="allocation", device_id="d-outside", demand_id="x")]
    scoped = DependencyScope("a", frozenset({"allocation"})).closure(data, [])
    assert scoped["system"] == {"a", "outside"}
