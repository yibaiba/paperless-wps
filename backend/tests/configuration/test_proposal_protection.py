from .test_proposal_generation import apply, call, draft_for, plan, published, read, write


def question_rows(client, draft, proposal):
    return call(
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


def test_manual_accessory_model_and_quantity_survive_regeneration(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    server = next(d for d in data["devices"] if d["quantity"] == "1")
    replacement = {
        k: v
        for k, v in server.items()
        if k not in {"generated_origin", "variant_snapshot", "source_snapshot", "origin_suggestion"}
    }
    replacement.update(
        variant_id=catalog["variants"][0]["id"], source_id=catalog["sources"][0]["id"], quantity="2"
    )
    draft = write(client, draft, [dict(action="device_put", value=replacement)])
    proposal = plan(client, draft)
    assert proposal["option"]["status"] == "conflict"
    assert any(q.get("status") == "conflict" for q in question_rows(client, draft, proposal))
    applied = apply(client, draft, proposal)
    actual = next(
        d for d in read(client, applied)["configuration"]["devices"] if d["id"] == server["id"]
    )
    assert actual["variant_id"] == replacement["variant_id"] and actual["quantity"] == "2"


def test_surplus_remove_cleans_drawing_and_quote(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    device = data["devices"][0]
    draft = write(client, draft, [dict(action="remove", collection="systems", id="system")])
    proposal = plan(client, draft)
    assert device["id"] in proposal["option"]["removal_candidates"]
    applied = write(
        client,
        draft,
        [
            dict(
                action="proposal_apply",
                proposal_id=proposal["proposal_id"],
                option_id=proposal["option"]["id"],
                fingerprint=proposal["fingerprint"],
                remove_device_ids=[device["id"]],
            )
        ],
    )
    actual = read(client, applied)["configuration"]
    assert actual["devices"] == [] and device["id"] not in actual["drawing_xml"]
    assert actual["quotation"]["prices"] == []


def test_unconfirmed_interpretation_is_a_question_not_requirement(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    generation = read(client, draft)["configuration"]["generation"]
    generation["sources"] = [
        dict(
            id="guess",
            object_id="system",
            field="inputs.seats",
            kind="agent_interpretation",
            confirmed=False,
            quote="也许48席",
        )
    ]
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    proposal = plan(client, draft)
    assert any(
        q["code"] == "interpretation_unconfirmed" and q["recipient"] == "customer"
        for q in question_rows(client, draft, proposal)
    )
    applied = apply(client, draft, proposal)
    assert read(client, applied)["configuration"]["devices"][0]["quantity"] == "32"


def test_web_and_mcp_apply_have_same_configuration_and_stale_guard(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    proposal = plan(client, draft)
    operation = dict(
        action="proposal_apply",
        proposal_id=proposal["proposal_id"],
        option_id=proposal["option"]["id"],
        fingerprint=proposal["fingerprint"],
    )
    preview = client.post(
        "/api/work-drafts/" + draft["id"] + "/preview",
        json=dict(expected_revision=draft["revision"], draft_version=1, operations=[operation]),
    )
    assert preview.status_code == 200, preview.text
    request = dict(
        draft_id=draft["id"],
        expected_revision=draft["revision"],
        operation_id="web-apply",
        operations=[operation],
    )
    result = client.post("/api/work-drafts/" + draft["id"] + "/edit", json=request)
    assert result.status_code == 200, result.text
    assert (
        client.post("/api/work-drafts/" + draft["id"] + "/edit", json=request).json()
        == result.json()
    )
    web_data = read(client, draft)["configuration"]
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=result.json()["revision"],
            operation_id="restore",
            checkpoint_revision=draft["revision"],
        ),
    )
    assert restored.status_code == 200, restored.text
    stale = client.post(
        "/api/list-tools/list_update",
        json=dict(
            request, expected_revision=restored.json()["revision"], operation_id="old-proposal"
        ),
    )
    assert stale.status_code == 409
    proposal2 = plan(client, restored.json())
    applied = apply(client, restored.json(), proposal2)
    mcp_data = read(client, applied)["configuration"]
    for data in (web_data, mcp_data):
        data.pop(
            "drawing_xml"
        )  # View IDs are independent; device references are asserted elsewhere.
        for device in data["devices"]:
            device["generated_origin"].pop("proposal_id")
    assert web_data == mcp_data


def test_locked_and_partially_reusable_accessory_choices():
    from types import SimpleNamespace

    from presales.configuration.projects.planning.accessory_choices import (
        locked_accessory,
        reusable_accessory,
    )

    device = dict(
        id="manual",
        variant_id="chosen",
        quantity="2",
        generated_origin=dict(key="accessory:need", variant_locked=True),
    )
    data = dict(devices=[device], accessory_allocations=[])
    demand = dict(
        id="need",
        missing="3",
        explanation={},
        rule=dict(target_variant_ids=["other"], allocation_mode="consumable"),
    )
    result, gaps, _ = locked_accessory(None, data, demand)
    assert result["devices"][0] == device
    assert result["accessory_allocations"][0]["quantity"] == "2"
    assert {q["code"] for q in gaps} == {"locked_accessory_conflict", "locked_accessory_quantity"}
    existing = dict(id="existing", variant_id="chosen", quantity="2", kind="accessory")
    variant = dict(id="chosen", source_ids=["source"], product=dict(name="隔离配件"), name="规格")
    generation = dict(supply_source="purchase", supply_evidence="隔离客户确认")
    data = dict(
        devices=[existing],
        accessory_allocations=[],
        supply_allocations=[],
        generation=generation,
        systems=[],
        requirements=[],
        knowledge_snapshot=[],
    )
    context = SimpleNamespace(
        deployment="independent",
        configuration=data,
        proposal_id="proposal",
        definitions={"definitions": [], "packages": []},
    )
    demand["rule"]["output_kind"] = "accessory"
    result, gaps, _ = reusable_accessory(
        context,
        data,
        variant=variant,
        demand=demand,
        demands=[demand],
        allowed={"existing"},
        gaps=[],
        ranking=[],
    )
    assert {d["id"]: d["quantity"] for d in result["devices"]}["existing"] == "2"
    assert sorted(a["quantity"] for a in result["accessory_allocations"]) == ["1", "2"]
    assert result["supply_allocations"][0]["quantity"] == "1"


def test_generation_evidence_rejects_missing_source(client):
    from .conftest import AUTHOR, BASE

    payload = dict(
        name="隔离错误依据",
        status="confirmed",
        roles=[
            dict(
                id="server",
                name="服务器",
                quantity_basis=dict(
                    status="confirmed",
                    mode="per_group",
                    factor="1",
                    **AUTHOR,
                    evidence_refs=[
                        dict(source_id="nonexistent", locator="Sheet1!A1", quote="虚构原文")
                    ],
                ),
            )
        ],
        **AUTHOR,
    )
    response = client.post(BASE + "/definitions", json=payload)
    assert response.status_code == 422
    assert "证据引用的来源不存在" in response.text
