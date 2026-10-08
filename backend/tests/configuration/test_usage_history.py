"""Old results are marked for recheck, not repaired by a second calculation path."""

from copy import deepcopy

from presales.configuration.projects.calculation.usage.differences import (
    check_differences,
    usage_differences,
)
from presales.configuration.projects.calculation.usage.versioning import projection_status
from presales.configuration.projects.services.lifecycle import procurement_diff
from presales.lists.schemas import GetList
from presales.lists.views import read_view

from .conftest import BASE
from .test_list_mcp import call, saved_project
from .test_web_drafts import start, write


def test_check_differences_keep_same_check_code_separate_by_system():
    before = dict(
        checks=[
            dict(kind="system", code="system_definition_unconfirmed", system_id="a", status="fail"),
            dict(kind="system", code="system_definition_unconfirmed", system_id="b", status="fail"),
        ]
    )
    after = deepcopy(before)
    after["checks"][0]["status"] = "pass"

    changes = check_differences(before, after)

    assert changes == [dict(previous=before["checks"][0], current=after["checks"][0])]


def test_recheck_adoption_persists_and_can_restore_old_check_without_fact_changes(client, catalog):
    from presales.configuration.projects.repository import ProjectConfigurations

    saved = saved_project(client, catalog)
    with client.app.state.session_factory() as session:
        record = ProjectConfigurations(session, client.app.state.quantity_engine).record(
            saved["project_id"]
        )
        historical = deepcopy(record.payload)
        historical.pop("usage_projection")
        record.payload = historical
        session.commit()
    old = client.get(BASE + "/projects/" + saved["project_id"]).json()
    draft = start(client, saved)
    assert draft["checked"]["usage_projection"]["current"] is False
    preview = client.post(
        BASE + "/projects/" + saved["project_id"] + "/change-preview",
        json=dict(
            expected_revision=1,
            configuration=draft["configuration"],
        ),
    ).json()
    request = dict(
        draft_id=draft["id"],
        expected_revision=1,
        expected_project_revision=1,
        operation_id="adopt-usage",
        fingerprint=preview["fingerprint"],
    )
    path = "/api/work-drafts/" + draft["id"]
    rejected = client.post(path + "/recheck", json=request | dict(fingerprint="stale-preview"))
    assert rejected.status_code == 409
    assert client.get(path).json()["revision"] == 1
    response = client.post(path + "/recheck", json=request)
    assert response.status_code == 200, response.text
    adopted = response.json()
    assert adopted["configuration"] == draft["configuration"]
    assert adopted["checked"]["usage_projection"]["version"] == 1
    assert adopted["revision"] == 2
    assert client.post(path + "/recheck", json=request).json() == adopted
    reopened = client.get(path).json()
    assert reopened["configuration"] == adopted["configuration"]
    assert reopened["checked"] == adopted["checked"] and reopened["revision"] == 2
    assert (
        client.post(path + "/recheck", json=request | dict(operation_id="conflict")).status_code
        == 409
    )
    restored = client.post(
        path + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=2,
            checkpoint_revision=1,
            operation_id="undo-usage",
        ),
    ).json()
    assert restored["checked"]["usage_projection"]["current"] is False
    assert restored["configuration"] == adopted["configuration"]
    assert client.get(BASE + "/projects/" + saved["project_id"]).json() == old


def test_recheck_refreshes_changes_against_the_saved_project(client, catalog):
    saved = saved_project(client, catalog)
    draft = start(client, saved)
    edited = write(
        client,
        draft,
        [dict(action="device_patch", device_id="server", note="重新检查后的备注")],
    )
    assert edited.status_code == 200, edited.text
    current = client.get("/api/work-drafts/" + draft["id"]).json()
    preview = client.post(
        BASE + "/projects/" + saved["project_id"] + "/change-preview",
        json=dict(expected_revision=1, configuration=current["configuration"]),
    ).json()
    adopted = client.post(
        "/api/work-drafts/" + draft["id"] + "/recheck",
        json=dict(
            draft_id=draft["id"],
            expected_revision=current["revision"],
            expected_project_revision=1,
            operation_id="recheck-refreshes-changes",
            fingerprint=preview["fingerprint"],
        ),
    )
    assert adopted.status_code == 200, adopted.text

    changes = call(client, "list_get", dict(draft_id=draft["id"], view="changes"))
    device_change = next(item for item in changes["items"] if item["kind"] == "devices")
    assert device_change["before"]["note"] == ""
    assert device_change["after"]["note"] == "重新检查后的备注"


def test_historical_status_does_not_rewrite_original_values():
    old = dict(configuration=dict(calculation_version=3), device_usages=[dict(device_id="old")])
    before = deepcopy(old)
    current = projection_status(old)
    assert current["usage_projection"]["current"] is False
    assert current["device_usages"] == old["device_usages"] and old == before
    assert projection_status(dict(configuration=dict(calculation_version=2))) == dict(
        configuration=dict(calculation_version=2)
    )


def test_mcp_usage_view_matches_saved_http_result_and_pages_by_device(client, catalog):
    saved = saved_project(client, catalog)
    http = client.get(BASE + "/projects/" + saved["project_id"]).json()
    request = dict(project_id=saved["project_id"], revision=1, view="device_usages", limit=1)
    mcp = call(client, "list_get", request)
    assert mcp["items"] == http["device_usages"][:1] and mcp["check_current"]
    assert mcp["usage_projection"]["fingerprint"] == http["usage_projection"]["fingerprint"]
    one = call(client, "list_get", request | dict(device_id="server"))
    assert one["total"] == 1 and one["items"][0]["device_id"] == "server"
    old = deepcopy(http)
    old.pop("usage_projection")
    old["device_usages"][0].pop("quantity_summary")
    assert read_view(old, GetList(**request))["check_current"] is False
    diff = usage_differences(old, http)
    assert diff[0]["device_id"] == "server" and diff[0]["previous"]["quantity_summary"] is None


def test_usage_trace_fields_do_not_report_a_procurement_change(client, catalog):
    saved = saved_project(client, catalog)
    current = client.get(BASE + "/projects/" + saved["project_id"]).json()
    line = current["project_output"]["lines"][0]
    current["project_output"]["procurement_lines"] = [line]
    old = deepcopy(current)
    previous = old["project_output"]["procurement_lines"][0]
    previous.pop("quantity_summary")
    for consumer in previous["consumers"]:
        for key in ("group_ids", "allocated_quantity", "fulfilled_by_demand_ids"):
            consumer.pop(key, None)
    assert procurement_diff(old, current) == []
    changed = deepcopy(current)
    changed["project_output"]["procurement_lines"][0]["quantity"] = "2"
    assert len(procurement_diff(old, changed)) == 1


def test_consumer_record_order_does_not_report_a_procurement_change():
    consumers = [
        dict(requirement_id="role", via="accessory", demand_id="first"),
        dict(requirement_id="role", via="accessory", demand_id="second"),
    ]
    before = dict(
        project_output=dict(
            procurement_lines=[dict(device_id="device", quantity="2", consumers=consumers)]
        )
    )
    after = deepcopy(before)
    after["project_output"]["procurement_lines"][0]["consumers"].reverse()
    assert procurement_diff(before, after) == []
    after["project_output"]["procurement_lines"][0]["quantity"] = "3"
    assert len(procurement_diff(before, after)) == 1
