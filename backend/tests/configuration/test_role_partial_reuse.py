from .test_proposal_evolution import change_seats
from .test_proposal_generation import apply, call, draft_for, plan, published, read, write


def existing_draft(client, catalog, *, ranked=True, quantities=("16",), accessory=False):
    definition, package = published(client, catalog, ranked=ranked, accessory=accessory)
    draft = draft_for(client, definition, package)
    data = read(client, draft)["configuration"]
    variant = catalog["variants"][0] if ranked else min(catalog["variants"], key=lambda v: v["id"])
    source = catalog["sources"][catalog["variants"].index(variant)]
    devices = [
        dict(
            id=f"existing-{index}",
            name="隔离已有终端",
            quantity=quantity,
            kind="hardware",
            variant_id=variant["id"],
            source_id=source["id"],
        )
        for index, quantity in enumerate(quantities)
    ]
    preference = dict(
        requirement_id=next(r["id"] for r in data["requirements"] if r["role_id"] == "terminal"),
        reusable_device_ids=[d["id"] for d in devices],
        evidence="客户确认可复用这些终端",
    )
    if ranked:
        preference["required_variant_id"] = variant["id"]
    operations = []
    for device in devices:
        operations.extend(
            [
                dict(action="device_put", value=device),
                dict(
                    action="supply_set",
                    device_id=device["id"],
                    allocations=[
                        dict(
                            id="supply-" + device["id"],
                            device_id=device["id"],
                            quantity=device["quantity"],
                            source="existing",
                            evidence="客户确认已有设备数量",
                        )
                    ],
                ),
            ]
        )
    return write(
        client,
        draft,
        [
            *operations,
            dict(
                action="requirements_patch",
                generation=dict(data["generation"], preferences=[preference]),
            ),
        ],
    )


def test_existing_16_only_buys_remaining_16_and_both_have_role_usage(client, catalog):
    draft = existing_draft(client, catalog)
    proposed = plan(client, draft)
    assert proposed["option"]["status"] != "conflict"
    applied = apply(client, draft, proposed)
    result = read(client, applied)
    data = result["configuration"]
    assert len(data["devices"]) == 2
    assert [d["quantity"] for d in data["devices"]] == ["16", "16"]
    assert [(a["source"], a["quantity"]) for a in data["supply_allocations"]] == [
        ("existing", "16"),
        ("purchase", "16"),
    ]
    assert len(data["requirements"]) == 1
    assert len(data["requirements"][0]["allocations"]) == 2
    assert result["checked"]["readiness"]["counts"]["requirements"] == 1
    assert result["checked"]["readiness"]["counts"]["selected_requirements"] == 1
    usages = result["checked"]["device_usages"]
    assert all(u["consumers"][0]["requirement_id"] == data["requirements"][0]["id"] for u in usages)
    assert not any(
        c["kind"] in {"assignment", "role_allocation"} and c["status"] != "pass"
        for c in result["checked"]["checks"]
    )


def test_multiple_batches_and_changed_quantity_reuse_ids(client, catalog):
    draft = existing_draft(client, catalog, quantities=("8", "8"))
    draft = apply(client, draft, plan(client, draft))
    before = read(client, draft)["configuration"]
    generated = next(d for d in before["devices"] if d.get("generated_origin"))
    draft = change_seats(client, draft, "48")
    draft = apply(client, draft, plan(client, draft))
    after = read(client, draft)["configuration"]
    assert next(d for d in after["devices"] if d["id"] == generated["id"])["quantity"] == "32"
    assert [d["quantity"] for d in after["devices"] if not d.get("generated_origin")] == ["8", "8"]
    draft = change_seats(client, draft, "24")
    draft = apply(client, draft, plan(client, draft))
    after = read(client, draft)["configuration"]
    assert next(d for d in after["devices"] if d["id"] == generated["id"])["quantity"] == "8"


def test_full_reuse_keeps_recommendation_gap(client, catalog):
    draft = existing_draft(client, catalog, ranked=False, quantities=("32",))
    proposal = plan(client, draft)
    assert proposal["option"]["device_count"] == 1
    assert proposal["option"]["standard"] is False
    questions = call(
        client,
        "list_get",
        dict(
            draft_id=draft["id"],
            proposal_id=proposal["proposal_id"],
            option_id=proposal["option"]["id"],
            view="proposal_questions",
            limit=100,
        ),
    )["items"]
    assert any(q["code"] == "recommendation_missing" for q in questions)


def test_only_allocated_part_of_larger_existing_batch_is_used(client, catalog):
    draft = existing_draft(client, catalog, quantities=("64",))
    draft = apply(client, draft, plan(client, draft))
    result = read(client, draft)
    data = result["configuration"]
    assert len(data["devices"]) == 1 and data["devices"][0]["quantity"] == "64"
    assert data["requirements"][0]["allocations"][0]["quantity"] == "32"
    assert not any(a["source"] == "purchase" for a in data["supply_allocations"])


def test_same_existing_quantity_is_not_reused_for_two_systems(client, catalog):
    draft = existing_draft(client, catalog)
    data = read(client, draft)["configuration"]
    system = dict(data["systems"][0], id="second", name="另一个会议室系统")
    draft = write(
        client,
        draft,
        [dict(action="requirements_patch", systems=[dict(system=system, features_confirmed=True)])],
    )
    data = read(client, draft)["configuration"]
    second = next(r for r in data["requirements"] if r["system_id"] == "second")
    generation = data["generation"]
    generation["preferences"].append(
        dict(generation["preferences"][0], requirement_id=second["id"])
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    assert sorted(
        a["quantity"] for a in data["supply_allocations"] if a["source"] == "purchase"
    ) == ["16", "32"]
    assert len(data["devices"]) == 3


def test_delete_restore_save_reopen_keep_role_allocations(client, catalog):
    draft = existing_draft(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    before = read(client, draft)["configuration"]
    generated = next(d for d in before["devices"] if d.get("generated_origin"))
    deleted = write(
        client, draft, [dict(action="remove", collection="devices", id=generated["id"])]
    )
    checked = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"],
            expected_revision=deleted["revision"],
            operation_id="partial-delete-check",
        ),
    )
    gaps = read(client, checked)["checked"]["checks"]
    assert any(c["kind"] == "role_allocation" and c["status"] == "conflict" for c in gaps)
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=checked["revision"],
            operation_id="partial-restore",
            checkpoint_revision=draft["revision"],
        ),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["configuration"] == before
    checked = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"],
            expected_revision=restored.json()["revision"],
            operation_id="partial-save-check",
        ),
    )
    saved = call(
        client,
        "list_save",
        dict(
            draft_id=draft["id"],
            expected_revision=checked["revision"],
            operation_id="partial-save",
            expected_project_revision=0,
            fingerprint=checked["check_fingerprint"],
        ),
    )
    reopened = client.get("/api/configuration/projects/" + saved["project_id"])
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["configuration"]["requirements"] == before["requirements"]
    assert len(reopened.json()["device_usages"]) == 2


def test_quantity_reduction_exposes_overallocated_device(client, catalog):
    draft = existing_draft(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    generated = next(d for d in data["devices"] if d.get("generated_origin"))
    draft = write(
        client, draft, [dict(action="device_patch", device_id=generated["id"], quantity="8")]
    )
    draft = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="overallocated-check",
        ),
    )
    assert any(
        c["kind"] == "role_allocation"
        and c["device_id"] == generated["id"]
        and c["status"] == "conflict"
        for c in read(client, draft)["checked"]["checks"]
        if c.get("device_id")
    )


def test_split_role_resources_are_not_guessed(client, catalog):
    draft = existing_draft(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    role = read(client, draft)["configuration"]["requirements"][0]
    role["resources"] = [dict(key="memory", amount="100", unit="GB", capacity_basis="unit")]
    draft = write(client, draft, [dict(action="requirement_put", value=role)])
    draft = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="resources-check",
        ),
    )
    assert any(
        c["code"] == "role_resource_distribution" and c["status"] == "unknown"
        for c in read(client, draft)["checked"]["checks"]
    )


def test_accessory_reuse_preserves_ranking_gap():
    from types import SimpleNamespace

    from presales.configuration.projects.planning.accessory_choices import reusable_accessory

    gap = dict(code="recommendation_missing", message="隔离缺少推荐依据")
    data = dict(
        devices=[dict(id="existing", variant_id="v", quantity="1")], accessory_allocations=[]
    )
    demand = dict(id="demand", missing="1", explanation={}, rule=dict(allocation_mode="consumable"))
    result = reusable_accessory(
        SimpleNamespace(deployment="independent"),
        data,
        variant=dict(id="v"),
        demand=demand,
        demands=[demand],
        allowed={"existing"},
        gaps=[gap],
        ranking=[],
    )
    assert result[1] == [gap]


def test_split_terminal_role_does_not_duplicate_server_accessory(client, catalog):
    draft = existing_draft(client, catalog, accessory=True)
    draft = apply(client, draft, plan(client, draft))
    result = read(client, draft)
    data = result["configuration"]
    assert len(data["devices"]) == 3
    server_role = next(r for r in data["requirements"] if r["role_id"] == "server")
    assert len(data["accessory_allocations"]) == 1
    allocation = data["accessory_allocations"][0]
    assert server_role["device_id"] == allocation["device_id"]
    assert allocation["quantity"] == "1"
    assert not any(c["kind"] == "sharing" for c in result["checked"]["checks"])


def test_decimal_remaining_quantity_is_preserved(client, catalog):
    draft = existing_draft(client, catalog, quantities=("16.5",))
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    assert [d["quantity"] for d in data["devices"]] == ["16.5", "15.5"]
    assert [a["quantity"] for a in data["requirements"][0]["allocations"]] == ["16.5", "15.5"]


def test_split_batches_count_device_and_environment_quantity_once(client, catalog):
    from decimal import Decimal

    from presales.configuration.projects.calculation.demands import contributions, direct_owners
    from presales.configuration.projects.role_allocations import project_allocations

    draft = existing_draft(client, catalog, accessory=True)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    for requirement in data["requirements"]:
        requirement["environment"] = [dict(key="seats", kind="quantity", value="32", unit="台")]
    projected, _ = project_allocations(data)
    rule = next(r for r in data["knowledge_snapshot"] if r["kind"] == "accessory")
    variants = {d["id"]: d["variant_snapshot"] for d in data["devices"]}
    for quantity_source in ["device_quantity", "environment"]:
        groups = contributions(
            projected,
            rule=dict(
                rule, quantity_source=quantity_source, quantity_key="seats", quantity_unit="台"
            ),
            owners=direct_owners(projected),
            variants=variants,
        )
        amounts = [entry["quantity"][0] for entries in groups.values() for entry in entries]
        assert sum(amounts, Decimal(0)) == 32


def test_seed_partial_browser_database(client, catalog, tmp_path):
    import json
    import os
    import sqlite3
    from pathlib import Path

    from .test_catalog_updates import COLUMN, publish

    for variant in catalog["variants"]:
        publish(client, variant, amount="100")
    draft = existing_draft(client, catalog)
    draft = write(
        client,
        draft,
        [
            dict(
                action="quotation_set",
                value=dict(price_column=COLUMN, price_adoption_date="2026-09-29"),
            )
        ],
    )
    checked = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="browser-partial-check",
        ),
    )
    saved = call(
        client,
        "list_save",
        dict(
            draft_id=draft["id"],
            expected_revision=checked["revision"],
            operation_id="browser-partial-save",
            expected_project_revision=0,
            fingerprint=checked["check_fingerprint"],
        ),
    )
    destination = Path(
        os.environ.get("PRESALES_PARTIAL_BROWSER_SEED", str(tmp_path / "partial.sqlite"))
    )
    with client.app.state.session_factory() as session, sqlite3.connect(destination) as connection:
        session.connection().connection.driver_connection.backup(connection)
    destination.with_suffix(".json").write_text(
        json.dumps(dict(project_id=saved["project_id"], draft_id=draft["id"]))
    )
    assert destination.exists()
