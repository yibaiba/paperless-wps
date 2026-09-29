import pytest

from .conftest import AUTHOR
from .test_proposal_evolution import two_systems
from .test_proposal_generation import apply, call, plan, read, write
from .test_proposal_prices_and_cycles import priced


@pytest.mark.parametrize("split", [False, True])
def test_regeneration_preserves_manual_fulfilled_role_binding(client, catalog, split):
    draft = two_systems(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    roles = [r for r in data["requirements"] if r["role_id"] == "server"]
    changed = dict(roles[0], device_id=roles[1]["device_id"])
    if split:
        changed.update(
            device_id=None,
            allocations=[
                dict(device_id=roles[1]["device_id"], quantity="1", evidence="隔离人工角色分配")
            ],
        )
    draft = write(client, draft, [dict(action="requirement_put", value=changed)])
    before = read(client, draft)["configuration"]
    assert (
        next(r for r in before["requirements"] if r["id"] == changed["id"])["device_id"]
        == changed["device_id"]
    )
    draft = apply(client, draft, plan(client, draft))
    after = read(client, draft)["configuration"]
    actual = next(r for r in after["requirements"] if r["id"] == changed["id"])
    assert actual["device_id"] == changed["device_id"], (
        "Manually changed server association was silently reset"
    )
    assert actual["allocations"] == changed["allocations"]
    assert changed["id"] in after["manual_edits"]["requirements"]


def test_pending_interpretation_survives_apply_check_and_confirmation(client, catalog, project):
    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    generation = dict(
        data["generation"],
        sources=[
            dict(
                id="unresolved",
                object_id="system",
                field="inputs.seats",
                kind="agent_interpretation",
                confirmed=False,
                quote="客户可能要求48席，尚待确认",
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    proposal = plan(client, draft)
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
    assert any(q["code"] == "interpretation_unconfirmed" for q in questions["items"])
    draft = apply(client, draft, proposal)
    actual = read(client, draft)
    url = "/api/configuration/projects/" + project["id"]
    saved = client.put(url, json=dict(expected_revision=0, configuration=actual["configuration"]))
    assert saved.status_code == 200, saved.text
    response = client.post(
        url + "/confirm",
        json=dict(expected_revision=1, fingerprint=saved.json()["fingerprint"], **AUTHOR),
    )
    assert response.status_code == 422, (
        f"Unresolved interpretation was confirmed; HTTP={response.status_code}"
    )


def test_regeneration_preserves_manual_allocation_evidence(client, catalog):
    draft = two_systems(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    allocation = data["accessory_allocations"][0]
    changed = dict(allocation, quantity="0.5", evidence="维护者核对：本次只确认一部分分配")
    draft = write(
        client,
        draft,
        [
            dict(action="accessory_remove", allocation_id=allocation["id"]),
            dict(action="accessory_link", value=changed),
        ],
    )
    assert (
        next(
            a
            for a in read(client, draft)["configuration"]["accessory_allocations"]
            if a["id"] == allocation["id"]
        )
        == changed
    )
    draft = apply(client, draft, plan(client, draft))
    after = read(client, draft)["configuration"]
    assert (
        next(a for a in after["accessory_allocations"] if a["id"] == allocation["id"]) == changed
    ), "Manual allocation evidence was overwritten"
    assert {d["id"]: d["quantity"] for d in after["devices"]} == {
        d["id"]: d["quantity"] for d in data["devices"]
    }
    suggestion = next(
        s
        for s in read(client, draft)["checked"]["suggestions"]
        if s["id"] == allocation["demand_id"]
    )
    assert suggestion["missing"] == "0.5"


def test_manual_binding_survives_reopen_and_undo_restores_automatic_binding(
    client, catalog, project
):
    draft = two_systems(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    checkpoint = draft["revision"]
    data = read(client, draft)["configuration"]
    roles = [r for r in data["requirements"] if r["role_id"] == "server"]
    changed = dict(roles[0], device_id=roles[1]["device_id"])
    draft = write(client, draft, [dict(action="requirement_put", value=changed)])
    saved = client.put(
        "/api/configuration/projects/" + project["id"],
        json=dict(expected_revision=0, configuration=read(client, draft)["configuration"]),
    )
    assert saved.status_code == 200, saved.text
    reopened = call(
        client,
        "list_create",
        dict(
            project_id=project["id"], revision=1, name="隔离重开", operation_id="reopen", **AUTHOR
        ),
    )
    reopened = apply(client, reopened, plan(client, reopened))
    actual = read(client, reopened)["configuration"]
    assert next(r for r in actual["requirements"] if r["id"] == changed["id"]) == changed
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            checkpoint_revision=checkpoint,
            operation_id="restore-manual-binding",
        ),
    )
    assert restored.status_code == 200, restored.text
    assert not restored.json()["configuration"]["manual_edits"]["requirements"]
    restored_draft = apply(client, restored.json(), plan(client, restored.json()))
    original = read(client, restored_draft)["configuration"]
    assert next(r for r in original["requirements"] if r["id"] == changed["id"]) == roles[0]


def test_partial_manual_included_allocation_is_preserved(client, catalog):
    from .test_included_content import update_variant
    from .test_proposal_generation import draft_for, published

    host, target = catalog["variants"]
    update_variant(
        client,
        host,
        included_items=[
            dict(
                id="bundled",
                name="隔离包含配置",
                variant_id=target["id"],
                kind="hardware",
                quantity="1",
                need_keys=["server"],
                status="confirmed",
                evidence=AUTHOR["evidence"],
            )
        ],
    )
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    allocation = data["included_allocations"][0]
    changed = dict(allocation, quantity="0.5", evidence="隔离仅确认部分抵扣")
    draft = write(
        client,
        draft,
        [
            dict(action="included_remove", allocation_id=allocation["id"]),
            dict(action="included_link", value=changed),
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    actual = read(client, draft)
    assert actual["configuration"]["included_allocations"] == [changed]
    assert actual["checked"]["suggestions"][0]["missing"] == "0.5"
    assert {d["id"]: d["quantity"] for d in actual["configuration"]["devices"]} == {
        d["id"]: d["quantity"] for d in data["devices"]
    }


def test_equivalent_manual_split_is_not_a_fulfillment_conflict(client, catalog):
    draft = two_systems(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    role = next(r for r in data["requirements"] if r["role_id"] == "server")
    value = dict(
        role,
        device_id=None,
        allocations=[
            dict(device_id=role["device_id"], quantity="1", evidence="隔离采用数量分配视图")
        ],
    )
    draft = write(client, draft, [dict(action="requirement_put", value=value)])
    proposal = plan(client, draft)
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
    assert not any(q["code"] == "manual_fulfillment_conflict" for q in questions["items"])
    draft = apply(client, draft, proposal)
    actual = read(client, draft)["configuration"]
    assert next(r for r in actual["requirements"] if r["id"] == role["id"]) == value
    draft = write(
        client, draft, [dict(action="remove", collection="devices", id=role["device_id"])]
    )
    assert role["id"] not in read(client, draft)["configuration"]["manual_edits"]["requirements"]
