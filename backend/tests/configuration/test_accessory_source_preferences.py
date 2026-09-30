from decimal import Decimal

import pytest

from .test_proposal_generation import apply, draft_for, plan, published, read, write
from .test_reuse_boundary_review import add_source_copy


def test_fulfilled_role_source_is_used_for_generated_accessory(client, catalog, workbook):
    add_source_copy(client, catalog, workbook)
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    role = next(r for r in data["requirements"] if r["role_id"] == "server")
    server = next(d for d in data["devices"] if d["id"] == role["device_id"])
    chosen = next(s for s in server["variant_snapshot"]["source_ids"] if s != server["source_id"])
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                requirement_id=role["id"],
                source_id=chosen,
                evidence="隔离指定服务器资料来源",
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    draft = apply(client, draft, plan(client, draft))
    actual = read(client, draft)
    server_after = next(d for d in actual["configuration"]["devices"] if d["id"] == server["id"])
    assert server_after["source_id"] == chosen
    assert not any(c["kind"] == "product_constraint" for c in actual["checked"]["checks"])


def accessory_draft(client, catalog, workbook):
    add_source_copy(client, catalog, workbook)
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    data = read(client, draft)["configuration"]
    role = next(r for r in data["requirements"] if r["role_id"] == "server")
    variant = next(
        v
        for v in client.get("/api/configuration/variants").json()
        if v["id"] == catalog["variants"][1]["id"]
    )
    return draft, role, variant


def with_preferences(client, draft, preferences):
    generation = dict(read(client, draft)["configuration"]["generation"], preferences=preferences)
    return write(client, draft, [dict(action="requirements_patch", generation=generation)])


def test_parent_source_does_not_override_accessory_source(client, catalog, workbook):
    draft, role, variant = accessory_draft(client, catalog, workbook)
    parent = next(
        r
        for r in read(client, draft)["configuration"]["requirements"]
        if r["role_id"] == "terminal"
    )
    chosen = max(variant["source_ids"])
    parent_source = catalog["sources"][0]["id"]
    draft = with_preferences(
        client,
        draft,
        [
            dict(requirement_id=parent["id"], source_id=parent_source, evidence="隔离终端来源"),
            dict(requirement_id=role["id"], source_id=chosen, evidence="隔离服务器来源"),
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    devices = {d["id"]: d for d in data["devices"]}
    assert {r["role_id"]: devices[r["device_id"]]["source_id"] for r in data["requirements"]} == {
        "terminal": parent_source,
        "server": chosen,
    }


@pytest.mark.parametrize("quantity", ["1", "0.5"])
def test_accessory_reuse_and_shortfall_both_use_selected_source(
    client, catalog, workbook, quantity
):
    draft, role, variant = accessory_draft(client, catalog, workbook)
    other_source, chosen = sorted(variant["source_ids"])
    operations = []
    for identity, source_id in [("other-stock", other_source), ("good-stock", chosen)]:
        device = dict(
            id=identity,
            name="隔离已有服务器",
            variant_id=variant["id"],
            source_id=source_id,
            quantity=quantity,
            kind="hardware",
        )
        operations.extend(
            [
                dict(action="device_put", value=device),
                dict(
                    action="supply_set",
                    device_id=identity,
                    allocations=[
                        dict(
                            id="supply-" + identity,
                            device_id=identity,
                            quantity=quantity,
                            source="existing",
                            evidence="隔离已有设备依据",
                        )
                    ],
                ),
            ]
        )
    draft = write(client, draft, operations)
    draft = with_preferences(
        client,
        draft,
        [
            dict(
                requirement_id=role["id"],
                source_id=chosen,
                reusable_device_ids=["other-stock", "good-stock"],
                evidence="隔离只采用指定来源",
            )
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    devices = {d["id"]: d for d in data["devices"]}
    allocations = data["accessory_allocations"]
    assert any(a["device_id"] == "good-stock" for a in allocations)
    assert all(devices[a["device_id"]]["source_id"] == chosen for a in allocations)
    generated_servers = [
        d for d in data["devices"] if d["variant_id"] == variant["id"] and d.get("generated_origin")
    ]
    assert sum((Decimal(d["quantity"]) for d in generated_servers), Decimal(0)) == 1 - Decimal(
        quantity
    )
    assert devices["other-stock"]["source_id"] == other_source


def test_conflicting_alias_sources_are_reported_without_arbitrary_purchase(
    client, catalog, workbook
):
    draft, role, variant = accessory_draft(client, catalog, workbook)
    second = dict(role, id="second-server-role")
    draft = write(client, draft, [dict(action="requirement_put", value=second)])
    draft = with_preferences(
        client,
        draft,
        [
            dict(
                requirement_id=requirement["id"],
                source_id=source_id,
                evidence="隔离不同来源要求",
            )
            for requirement, source_id in zip(
                [role, second], sorted(variant["source_ids"]), strict=True
            )
        ],
    )
    proposal = plan(client, draft)
    assert proposal["option"]["status"] == "conflict"
    from .test_proposal_generation import call

    questions = call(
        client,
        "list_get",
        dict(
            draft_id=draft["id"],
            proposal_id=proposal["proposal_id"],
            option_id=proposal["option"]["id"],
            view="proposal_questions",
        ),
    )["items"]
    gap = next(q for q in questions if q["code"] == "accessory_source_conflict")
    assert {p["requirement_id"] for p in gap["evidence"]} == {role["id"], second["id"]}
    draft = apply(client, draft, proposal)
    data = read(client, draft)["configuration"]
    assert not data["accessory_allocations"]
    assert not any(d["variant_id"] == variant["id"] for d in data["devices"])


def test_manual_accessory_source_lock_is_not_overridden_by_preference(client, catalog, workbook):
    draft, role, variant = accessory_draft(client, catalog, workbook)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    server = next(d for d in data["devices"] if d["variant_id"] == variant["id"])
    alternate = next(s for s in variant["source_ids"] if s != server["source_id"])
    value = {k: server[k] for k in ["id", "name", "variant_id", "quantity", "kind"]}
    value["source_id"] = alternate
    draft = write(client, draft, [dict(action="device_put", value=value)])
    draft = with_preferences(
        client,
        draft,
        [
            dict(
                requirement_id=role["id"],
                source_id=server["source_id"],
                evidence="隔离与人工选型冲突",
            )
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    result = read(client, draft)
    assert (
        next(d for d in result["configuration"]["devices"] if d["id"] == server["id"])["source_id"]
        == alternate
    )
    assert any(
        c["kind"] == "product_constraint" and c["status"] == "conflict"
        for c in result["checked"]["checks"]
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_shared_scope_resolves_all_consumers_without_leaking_other_scopes(reverse):
    from copy import deepcopy
    from types import SimpleNamespace

    from presales.configuration.projects.planning.accessory_preferences import accessory_selection

    tasks, preferences = [], {}
    for system in ["one", "two", "unrelated"]:
        parent_id, alias_id = system + "-parent", system + "-alias"
        tasks.extend(
            [
                dict(
                    system=dict(id=system), role=dict(id="parent"), requirement=dict(id=parent_id)
                ),
                dict(
                    system=dict(id=system),
                    role=dict(
                        id="server",
                        fulfilled_by=dict(
                            role_id="parent",
                            need_key="server",
                            status="confirmed",
                        ),
                    ),
                    requirement=dict(id=alias_id),
                ),
            ]
        )
        preferences[parent_id] = dict(reusable_device_ids=[parent_id], source_id="parent-source")
        preferences[alias_id] = dict(
            reusable_device_ids=[alias_id],
            source_id="chosen" if system == "two" else "unrelated" if system == "unrelated" else "",
        )
    original = deepcopy(tasks)
    if reverse:
        tasks = list(reversed(tasks))
    context = SimpleNamespace(preference=lambda identity: preferences[identity])
    selection, gap = accessory_selection(
        context,
        tasks=tasks,
        demand=dict(
            id="room-need",
            need_key="server",
            consumer_requirement_ids=["one-parent", "two-parent"],
        ),
    )
    assert gap is None
    assert selection == dict(
        source_id="chosen", allowed={"one-parent", "two-parent", "one-alias", "two-alias"}
    )
    assert sorted(tasks, key=lambda t: t["requirement"]["id"]) == sorted(
        original, key=lambda t: t["requirement"]["id"]
    )
