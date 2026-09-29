from copy import deepcopy
from uuid import uuid4

from .conftest import BASE, post
from .test_included_content import allocation, checked_with, update_variant
from .test_included_content import included as included
from .test_web_drafts import start, write


def review_operations(value, **changes):
    return [
        dict(action="included_remove", allocation_id=value["id"]),
        dict(action="included_link", value={**value, **changes}),
    ]


def saved_workspace(client, checked, project):
    response = client.put(
        BASE + "/projects/" + project["id"],
        json=dict(expected_revision=0, configuration=checked["configuration"]),
    )
    assert response.status_code == 200, response.text
    return start(client, response.json())


def test_review_exposes_invalid_credit_and_current_basis(client, included):
    credit = allocation(included)
    previous = checked_with(client, included, [credit])
    passed = previous["suggestions"][0]["included_allocation_checks"][0]
    assert passed["counted_quantity"] == "1"
    assert passed["capacity"] == passed["allocated_quantity"] == "1"
    update_variant(
        client,
        included["host"],
        included_items=[{**included["fact"], "evidence": "新修订已明确包含的隔离依据"}],
    )
    refreshed = post(
        client, "/check", dict(configuration=previous["configuration"], refresh_knowledge=True)
    )
    check = refreshed["suggestions"][0]["included_allocation_checks"][0]
    assert check["allocation_id"] == credit["id"]
    assert check["status"] == "unknown" and check["counted_quantity"] == "0"
    assert check["current_host_variant_revision"] == 3
    assert check["current_evidence"] == "新修订已明确包含的隔离依据"
    project_check = next(c for c in refreshed["checks"] if c["kind"] == "included_allocation")
    assert {key: project_check[key] for key in check if key != "action"} == {
        key: value for key, value in check.items() if key != "action"
    }
    assert project_check["code"] == "included_allocation"
    assert dict(kind="allocation", id=credit["id"]) in project_check["objects"]
    assert previous["suggestions"][0]["included_allocation_checks"][0] == passed


def test_invalid_replacement_is_atomic_and_valid_review_is_undoable(client, included, project):
    credit = allocation(included)
    checked = checked_with(client, included, [credit])
    web = saved_workspace(client, checked, project)
    rejected = write(client, web, review_operations(credit, quantity="2", evidence="超过包含数量"))
    assert rejected.status_code == 422, rejected.text
    retained = client.get("/api/work-drafts/" + web["id"]).json()
    assert retained["revision"] == web["revision"]
    assert retained["configuration"]["included_allocations"] == [credit]
    command = review_operations(credit, quantity="0.5", evidence="核对后采用一半")
    operation_id = str(uuid4())
    applied = write(client, retained, command, operation_id=operation_id)
    assert applied.status_code == 200, applied.text
    assert write(client, retained, command, operation_id=operation_id).json() == applied.json()
    latest = client.get("/api/work-drafts/" + web["id"]).json()
    assert latest["configuration"]["included_allocations"][0]["id"] == credit["id"]
    assert latest["checked"]["suggestions"][0]["included_quantity"] == "0.5"
    assert latest["checked"]["suggestions"][0]["missing"] == "0.5"
    restored = client.post(
        "/api/work-drafts/" + web["id"] + "/restore",
        json=dict(
            draft_id=web["id"],
            expected_revision=latest["revision"],
            checkpoint_revision=web["revision"],
            operation_id=str(uuid4()),
        ),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["configuration"]["included_allocations"] == [credit]


def test_explicit_reconfirmation_adopts_current_revision_only(client, included, project):
    credit = allocation(included)
    original = checked_with(client, included, [credit])
    update_variant(client, included["host"], name="隔离新修订配置")
    refreshed = post(
        client, "/check", dict(configuration=original["configuration"], refresh_knowledge=True)
    )
    assert refreshed["suggestions"][0]["missing"] == "1"
    web = saved_workspace(client, refreshed, project)
    response = write(
        client, web, review_operations(credit, host_variant_revision=3, evidence="明确核对当前配置")
    )
    assert response.status_code == 200, response.text
    current = client.get("/api/work-drafts/" + web["id"]).json()
    assert current["checked"]["suggestions"][0]["missing"] == "0"
    assert current["configuration"]["included_allocations"][0]["host_variant_revision"] == 3
    assert original["configuration"]["included_allocations"][0]["host_variant_revision"] == 2


def test_capacity_conflict_explains_requested_and_counted_quantity(client, included):
    data = deepcopy(included["checked"]["configuration"])
    data["included_allocations"] = [allocation(included)]
    data["devices"][0]["quantity"] = "0.5"
    result = post(client, "/check", dict(configuration=data))
    check = result["suggestions"][0]["included_allocation_checks"][0]
    assert (check["capacity"], check["allocated_quantity"], check["counted_quantity"]) == (
        "0.5",
        "1",
        "0",
    )
    assert check["status"] == "conflict"
