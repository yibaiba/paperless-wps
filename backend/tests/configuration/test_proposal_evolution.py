from copy import deepcopy
from uuid import uuid4

from .conftest import AUTHOR, post
from .test_proposal_generation import apply, call, draft_for, plan, published, read, write


def change_seats(client, draft, value):
    system = read(client, draft)["configuration"]["systems"][0]
    system["inputs"][0]["value"] = value
    return write(
        client,
        draft,
        [dict(action="requirements_patch", systems=[dict(system=system, features_confirmed=True)])],
    )


def test_quantity_changes_locks_idempotency_and_undo(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    proposal = plan(client, draft)
    operation = dict(
        action="proposal_apply",
        proposal_id=proposal["proposal_id"],
        option_id=proposal["option"]["id"],
        fingerprint=proposal["fingerprint"],
    )
    request = dict(
        draft_id=draft["id"],
        expected_revision=draft["revision"],
        operation_id="apply-once",
        operations=[operation],
    )
    applied = call(client, "list_update", request)
    assert call(client, "list_update", request) == applied
    before = read(client, applied)["configuration"]
    changed = change_seats(client, applied, "48")
    next_proposal = plan(client, changed)
    updated = apply(client, changed, next_proposal)
    after = read(client, updated)["configuration"]
    assert {d["id"] for d in before["devices"]} == {d["id"] for d in after["devices"]}
    assert {d["quantity"] for d in after["devices"]} == {"48", "1"}
    terminal = next(d for d in after["devices"] if d["quantity"] == "48")
    locked = write(
        client,
        updated,
        [
            dict(action="device_patch", device_id=terminal["id"], quantity="50"),
            dict(
                action="price_set",
                value=dict(
                    device_id=terminal["id"],
                    variant_id=terminal["variant_id"],
                    source_id=terminal["source_id"],
                    mode="manual",
                    unit_price="0",
                    evidence="隔离零价授权",
                ),
            ),
        ],
    )
    newer = change_seats(client, locked, "64")
    protected = apply(client, newer, plan(client, newer))
    result = read(client, protected)["configuration"]
    assert next(d for d in result["devices"] if d["id"] == terminal["id"])["quantity"] == "50"
    assert (
        next(p for p in result["quotation"]["prices"] if p["device_id"] == terminal["id"])[
            "unit_price"
        ]
        == "0"
    )
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=protected["revision"],
            checkpoint_revision=applied["revision"],
            operation_id="undo-generated",
        ),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["configuration"] == before


def test_backtracks_after_downstream_capacity_conflict(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    data = read(client, draft)["configuration"]
    role = data["requirements"][0]
    role["resources"] = [dict(key="memory", amount="3072", unit="GB", capacity_basis="unit")]
    draft = write(client, draft, [dict(action="requirement_put", value=role)])
    result = apply(client, draft, plan(client, draft))
    device = read(client, result)["configuration"]["devices"][0]
    assert device["variant_id"] == catalog["variants"][1]["id"]


def two_systems(client, catalog, *, shared=False):
    definition, package = published(client, catalog, accessory=True)
    booking, booking_package = published(client, catalog, accessory=True)
    if shared:
        post(
            client,
            "/knowledge",
            dict(
                name="隔离共享依据",
                kind="sharing",
                status="confirmed",
                selector=dict(variant_ids=[catalog["variants"][1]["id"]]),
                shared_role_refs=[
                    dict(system_definition_id=d["id"], role_id="terminal")
                    for d in (definition, booking)
                ],
                **AUTHOR,
            ),
        )
    draft = draft_for(client, definition, package)
    new_system = dict(
        id="booking",
        room_id="room",
        name="会议预约隔离系统",
        kind=booking["name"],
        definition_id=booking["id"],
        knowledge_package_id=booking_package["id"],
        inputs=[dict(key="seats", kind="quantity", value="2", unit="台")],
    )
    return write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                systems=[dict(system=new_system, features_confirmed=True)],
            )
        ],
    )


def test_independent_and_shared_without_and_with_evidence(client, catalog):
    draft = two_systems(client, catalog)
    independent = plan(client, draft)
    assert independent["option"]["device_count"] == 4
    shared = plan(client, draft, deployment="shared")
    assert shared["option"]["device_count"] == 3
    applied = apply(client, draft, shared)
    checked = read(client, applied)["checked"]
    assert next(c for c in checked["checks"] if c["kind"] == "sharing")["status"] == "unknown"
    refs = [
        dict(system_definition_id=s["definition_id"], role_id="terminal")
        for s in checked["configuration"]["systems"]
    ]
    rule = post(
        client,
        "/knowledge",
        dict(
            name="隔离共享依据",
            kind="sharing",
            status="confirmed",
            selector=dict(variant_ids=[catalog["variants"][1]["id"]]),
            shared_role_refs=refs,
            **AUTHOR,
        ),
    )
    from .package_helpers import publish_members

    publish_members(client, checked["configuration"]["systems"], [rule])
    upgraded = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"],
            expected_revision=applied["revision"],
            operation_id="upgrade-test",
            refresh_knowledge=True,
        ),
    )
    verified = read(client, upgraded)["checked"]
    assert next(c for c in verified["checks"] if c["kind"] == "sharing")["status"] == "pass"
    server = next(
        d
        for d in verified["configuration"]["devices"]
        if d["variant_id"] == catalog["variants"][1]["id"]
    )
    removed = write(
        client, upgraded, [dict(action="remove", collection="devices", id=server["id"])]
    )
    assert (
        len([s for s in read(client, removed)["checked"]["suggestions"] if s["missing"] == "1"])
        == 2
    )


def test_existing_server_only_explicitly_reused(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    server = dict(
        id="customer-server",
        name="客户服务器",
        variant_id=catalog["variants"][1]["id"],
        source_id=catalog["sources"][1]["id"],
        quantity="1",
        kind="hardware",
    )
    draft = write(
        client,
        draft,
        [
            dict(action="device_put", value=server),
            dict(
                action="supply_set",
                device_id=server["id"],
                allocations=[
                    dict(
                        id="existing-supply",
                        device_id=server["id"],
                        quantity="1",
                        source="existing",
                        evidence=AUTHOR["evidence"],
                    )
                ],
            ),
        ],
    )
    data = read(client, draft)["configuration"]
    role = next(r for r in data["requirements"] if r["role_id"] == "server")
    generation = {
        **data["generation"],
        "preferences": [
            dict(
                requirement_id=role["id"],
                reusable_device_ids=[server["id"]],
                evidence=AUTHOR["evidence"],
            )
        ],
    }
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    applied = apply(client, draft, plan(client, draft))
    actual = read(client, applied)
    assert len(actual["configuration"]["devices"]) == 2
    assert not any(
        d["device_id"] == server["id"]
        for d in actual["checked"]["project_output"]["procurement_lines"]
    )


def test_unconfirmed_agent_interpretation_not_effective(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    before = read(client, draft)
    system = deepcopy(before["configuration"]["systems"][0])
    system["inputs"][0]["value"] = "99"
    payload = dict(
        draft_id=draft["id"],
        expected_revision=draft["revision"],
        operation_id=str(uuid4()),
        operations=[
            dict(
                action="requirements_patch",
                systems=[dict(system=system)],
                generation=dict(
                    sources=[
                        dict(
                            id="guess",
                            object_id="system",
                            field="inputs.seats",
                            kind="agent_interpretation",
                            confirmed=False,
                            quote="可能99席",
                        )
                    ]
                ),
            )
        ],
    )
    response = client.post("/api/list-tools/list_update", json=payload)
    assert response.status_code == 422
    assert read(client, draft) == before


def test_shared_capacity_conflict_backtracks_to_separate_servers(client, catalog):
    draft = two_systems(client, catalog, shared=True)
    data = read(client, draft)["configuration"]
    operations = []
    for requirement in data["requirements"]:
        if requirement["role_id"] == "terminal":
            value = dict(
                requirement,
                resources=[
                    dict(
                        key="memory",
                        amount="80",
                        unit="GB",
                        applies_to="accessory",
                        target_need_key="server",
                        capacity_basis="deployment",
                    )
                ],
            )
            operations.append(dict(action="requirement_put", value=value))
    draft = write(client, draft, operations)
    proposal = plan(client, draft, deployment="shared")
    applied = apply(client, draft, proposal)
    result = read(client, applied)
    servers = [
        d
        for d in result["configuration"]["devices"]
        if d["variant_id"] == catalog["variants"][1]["id"]
    ]
    assert len(servers) == 2
    assert not any(c["status"] == "conflict" for c in result["checked"]["checks"])


def test_zero_demand_reports_existing_generated_surplus(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    draft = change_seats(client, draft, "0")
    proposal = plan(client, draft)
    assert proposal["option"]["removal_candidates"]
    questions = call(
        client,
        "list_get",
        dict(
            draft_id=draft["id"],
            proposal_id=proposal["proposal_id"],
            option_id=proposal["option"]["id"],
            view="proposal_questions",
        ),
    )
    assert any(q["code"] == "quantity_zero_surplus" for q in questions["items"])
    assert read(client, draft)["configuration"]["devices"][0]["quantity"] == "32"
