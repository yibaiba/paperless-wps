"""Room and system demands cannot independently spend the same bundled units."""

from copy import deepcopy
from uuid import uuid4

import pytest

from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import BASE, post
from .test_included_partitions import credit
from .test_included_partitions import partitioned as partitioned


@pytest.fixture
def overlapping(client, partitioned):
    data = deepcopy(partitioned["configuration"])
    first = data["requirements"][0]
    first["allocations"][0]["quantity"] = "4"
    data["requirements"].append(dict(deepcopy(first), id="r3", role="另一类终端"))
    original = data["knowledge_snapshot"][0]
    rule = post(
        client,
        "/knowledge",
        {
            **{k: v for k, v in original.items() if k in KnowledgeInput.model_fields},
            "name": "隔离：房间内指定角色的授权需求",
            "role": "终端",
            "calculation_scope": "room",
        },
    )
    result = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    system = next(
        s
        for s in result["suggestions"]
        if s["rule"]["id"] == original["id"] and s["scope_id"] == "paper"
    )
    room = next(
        s
        for s in result["suggestions"]
        if s["rule"]["id"] == rule["id"] and s["scope_id"] == "room"
    )
    return result, system, room


def credits(result, system, room, *, amounts=("8", "4")):
    template = credit(result)
    return [
        dict(template, id=identity, demand_id=demand["id"], quantity=quantity)
        for identity, demand, quantity in (
            ("system-credit", system, amounts[0]),
            ("room-credit", room, amounts[1]),
        )
    ]


def test_nested_demands_cannot_borrow_from_unrelated_room(client, overlapping):
    result, system, room = overlapping
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=credits(result, system, room),
            )
        ),
    )
    checks = [c for c in checked["checks"] if c["kind"] == "included_allocation"]
    assert len(checks) == 2
    assert all(c["status"] == "conflict" and c["counted_quantity"] == "0" for c in checks)


def test_credit_issue_actions_only_target_the_demands_actual_roles(client, overlapping):
    result, system, room = overlapping
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=credits(result, system, room),
            )
        ),
    )
    checks = {
        c["allocation_id"]: c for c in checked["checks"] if c["kind"] == "included_allocation"
    }
    assert set(checks["system-credit"]["action"]["requirement_ids"]) == {"r1", "r3"}
    assert checks["room-credit"]["action"]["requirement_ids"] == ["r1"]
    assert all(dict(kind="requirement", id="r2") not in c["objects"] for c in checks.values())


@pytest.mark.parametrize("first_scope", ["system", "room"])
def test_offer_respects_reservations_in_containing_and_contained_scopes(
    client, overlapping, first_scope
):
    result, system, room = overlapping
    allocations = credits(result, system, room)
    chosen, other, expected = (
        (allocations[0], room, "0") if first_scope == "system" else (allocations[1], system, "4")
    )
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=[chosen],
            )
        ),
    )
    demand = next(s for s in checked["suggestions"] if s["id"] == other["id"])
    assert demand["included_offers"][0]["available"] == expected


def test_edit_rejects_nested_double_credit_atomically(client, overlapping, project):
    result, system, room = overlapping
    values = credits(result, system, room)
    response = client.post(
        BASE + "/projects/" + project["id"] + "/edit-preview",
        json=dict(
            configuration=result["configuration"],
            expected_revision=0,
            draft_version=0,
            operations=[dict(action="included_link", value=value) for value in values],
        ),
    )
    assert response.status_code == 422, response.status_code


def test_compatible_nested_credits_keep_unrelated_room_available(client, overlapping):
    result, system, room = overlapping
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=credits(result, system, room, amounts=("4", "4")),
            )
        ),
    )
    assert all(
        c["status"] == "pass" for c in checked["checks"] if c["kind"] == "included_allocation"
    )
    second = next(s for s in checked["suggestions"] if s["scope_id"] == "booking")
    assert second["included_offers"][0]["available"] == "24"


def test_remove_retry_restore_and_failed_batch_keep_scope_reservations(
    client, overlapping, project
):
    from .test_included_review import saved_workspace
    from .test_web_drafts import write

    result, system, room = overlapping
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=credits(result, system, room, amounts=("4", "4")),
            )
        ),
    )
    draft = saved_workspace(client, checked, project)
    original = client.get("/api/work-drafts/" + draft["id"]).json()
    rejected = write(
        client,
        draft,
        [
            dict(action="included_remove", allocation_id="room-credit"),
            dict(
                action="included_link", value=dict(credits(result, system, room)[1], quantity="8")
            ),
        ],
    )
    assert rejected.status_code == 422
    assert client.get("/api/work-drafts/" + draft["id"]).json() == original
    operation_id = str(uuid4())
    command = [dict(action="included_remove", allocation_id="room-credit")]
    removed = write(client, draft, command, operation_id=operation_id)
    assert removed.status_code == 200, removed.text
    assert write(client, draft, command, operation_id=operation_id).json() == removed.json()
    current = client.get("/api/work-drafts/" + draft["id"]).json()
    for identity in (system["id"], room["id"]):
        demand = next(s for s in current["checked"]["suggestions"] if s["id"] == identity)
        assert demand["included_offers"][0]["available"] == "4"
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=current["revision"],
            checkpoint_revision=draft["revision"],
            operation_id=str(uuid4()),
        ),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["configuration"] == original["configuration"]


@pytest.mark.parametrize("amounts", [("3.5", "4.5"), ("0.5", "3.5")])
def test_decimal_credits_use_exact_scope_capacities(client, overlapping, amounts):
    result, system, room = overlapping
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=credits(result, system, room, amounts=amounts),
            )
        ),
    )
    checks = {
        c["allocation_id"]: c for c in checked["checks"] if c["kind"] == "included_allocation"
    }
    assert checks["system-credit"]["status"] == "pass"
    assert checks["room-credit"]["status"] == ("conflict" if amounts[1] == "4.5" else "pass")
