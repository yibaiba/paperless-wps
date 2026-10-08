from copy import deepcopy
from uuid import NAMESPACE_URL, uuid4, uuid5

from presales.configuration.projects.planning.combination_steps import selected_groups
from presales.wps.next_edit_projection import deferred_combination

from .conftest import AUTHOR, post
from .test_proposal_generation import published
from .test_wps_business_context import entity_versions, setup_workbook


def completion_body(
    client, catalog, *, quantity=True, accessory=True, ranked=True, output_kind="hardware"
):
    definition, package = published(
        client,
        catalog,
        quantity=quantity,
        accessory=accessory,
        ranked=ranked,
        output_kind=output_kind,
    )
    headers, _, _, body = setup_workbook(client, catalog)
    body.update(
        lines=[],
        local_revision=0,
        query="",
        scope=dict(
            sheet="报价表",
            start_row=3,
            end_row=50,
            room_id="room",
            system_id="system",
            requirement_id=None,
        ),
        active_cell=dict(sheet="报价表", row=3, column=2, values={}),
        target_cells=[dict(sheet="报价表", row=4, column=2, values={})],
    )
    body["business_operations"] = [
        {
            "action": "system_setup",
            "features_confirmed": True,
            "new_room": {"id": "room", "name": "隔离会议室"},
            "system": {
                "id": "system",
                "name": "隔离系统",
                "kind": "隔离红盾 Windows",
                "room_id": "room",
                "definition_id": definition["id"],
                "knowledge_package_id": package["id"],
                "inputs": [{"key": "seats", "kind": "quantity", "value": "3", "unit": "台"}],
            },
            "role_ids": ["terminal"],
        },
        {
            "action": "requirements_patch",
            "generation": {
                "features_confirmed": ["system"],
                "supply_source": "purchase",
                "supply_evidence": "隔离测试明确采购需求",
            },
        },
    ]
    return headers, body


def preview(client, headers, body):
    response = client.post("/api/wps/completion/preview", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def combination_completion_body(client, catalog, *, mode="require_all"):
    terminal, addon = catalog["variants"][:2]
    quantity = dict(status="confirmed", scope="system", mode="per_group", factor="1", **AUTHOR)
    definition = post(
        client,
        "/definitions",
        dict(
            name="ZEN 下一步编辑",
            status="confirmed",
            roles=[
                dict(id="terminal", name="终端", required=True, quantity_basis=quantity),
                dict(id="addon", name="配套", required=False, quantity_basis=quantity),
            ],
            **AUTHOR,
        ),
    )
    rules = [
        post(
            client,
            "/knowledge",
            dict(
                name=name,
                kind="suitability",
                status="confirmed",
                system_definition_id=definition["id"],
                role_id=role,
                selector=dict(variant_ids=[variant["id"]]),
                **AUTHOR,
            ),
        )
        for name, role, variant in (
            ("终端适用", "terminal", terminal),
            ("配套适用", "addon", addon),
        )
    ]
    rules.append(
        post(
            client,
            "/knowledge",
            dict(
                schema_version=2,
                name="终端组合要求",
                kind="combination",
                status="confirmed",
                selector=dict(variant_ids=[terminal["id"]]),
                combination=dict(
                    mode=mode,
                    scope="system",
                    targets=[
                        dict(
                            id="addon",
                            name="配套",
                            system_definition_id=definition["id"],
                            role_id="addon",
                            variant_ids=[addon["id"]],
                        )
                    ],
                ),
                **AUTHOR,
            ),
        )
    )
    package = post(
        client,
        "/knowledge-packages",
        dict(
            name="ZEN 下一步编辑包",
            branch="Windows",
            system_definition_id=definition["id"],
            definition_revision=definition["revision"],
            status="published",
            members=[dict(id=rule["id"], revision=rule["revision"]) for rule in rules],
            coverage=[
                dict(
                    role_id=role,
                    selector=dict(variant_ids=[variant["id"]]),
                    accessories="none",
                    resources="not_applicable",
                    evidence=AUTHOR["evidence"],
                )
                for role, variant in (("terminal", terminal), ("addon", addon))
            ],
            recommendations=[
                dict(
                    role_id=role,
                    variant_ids=[variant["id"]],
                    status="confirmed",
                    **AUTHOR,
                )
                for role, variant in (("terminal", terminal), ("addon", addon))
            ],
            **AUTHOR,
        ),
    )
    headers, _, _, body = setup_workbook(client, catalog)
    body.update(
        lines=[],
        local_revision=0,
        query="",
        scope=dict(
            sheet="报价表",
            start_row=3,
            end_row=50,
            room_id="room",
            system_id="system",
            requirement_id=None,
        ),
        active_cell=dict(sheet="报价表", row=3, column=2, values={}),
        target_cells=[dict(sheet="报价表", row=4, column=2, values={})],
        business_operations=[
            {
                "action": "system_setup",
                "features_confirmed": True,
                "new_room": {"id": "room", "name": "ZEN 会议室"},
                "system": {
                    "id": "system",
                    "name": "ZEN 系统",
                    "kind": "ZEN 下一步编辑",
                    "room_id": "room",
                    "definition_id": definition["id"],
                    "knowledge_package_id": package["id"],
                    "inputs": [],
                },
                "role_ids": ["terminal"],
            },
            {
                "action": "requirements_patch",
                "generation": {
                    "features_confirmed": ["system"],
                    "supply_source": "purchase",
                    "supply_evidence": "隔离测试",
                },
            },
        ],
    )
    return headers, body


def accept(body, item):
    result = deepcopy(body)
    for binding in item["line_bindings"]:
        values = {p["field"]: p["after"] for p in item["patches"] if p["row"] == binding["row"]}
        identity = {
            k: v
            for k, v in binding.items()
            if k not in {"confirmed_values", "anchor_fingerprint", "requirement_id"}
        }
        result["lines"].append({**identity, **values})
    result["business_operations"].extend(item["business_operations"])
    result["local_revision"] += 1
    result["active_cell"]["row"] += 1
    result["target_cells"][0]["row"] += 1
    return result


def test_role_then_required_accessory_preview_is_read_only_http(client, catalog):
    headers, body = completion_body(client, catalog)
    before = entity_versions(client)
    first = preview(client, headers, body)
    assert first["items"], first
    item = first["items"][0]
    assert item["applicable"], item["issues"]
    assert item["line_bindings"][0]["variant_id"] == catalog["variants"][0]["id"]
    assert any(p["field"] == "quantity" and p["after"] == "3" for p in item["patches"])
    second_body = accept(body, item)
    second = preview(client, headers, second_body)
    assert second["items"], second
    item2 = second["items"][0]
    assert item2["line_bindings"][0]["variant_id"] == catalog["variants"][1]["id"]
    assert any(op["action"] == "accessory_link" for op in item2["business_operations"])
    assert entity_versions(client) == before


def test_missing_quantity_evidence_produces_questions_not_guessed_product(client, catalog):
    headers, body = completion_body(client, catalog, quantity=False)
    result = preview(client, headers, body)
    assert not result["items"]
    assert any(q.get("code") == "role_quantity_missing" for q in result["issues"])


def test_mismatched_room_and_stale_revision_are_errors(client, catalog):
    headers, body = completion_body(client, catalog)
    body["scope"]["room_id"] = "different-room"
    assert client.post("/api/wps/completion/preview", headers=headers, json=body).status_code == 422
    body["scope"]["room_id"] = "room"
    body["expected_draft_revision"] += 1
    assert client.post("/api/wps/completion/preview", headers=headers, json=body).status_code == 409


def test_dismissed_step_is_not_repeated_and_formulas_cannot_apply(client, catalog):
    headers, body = completion_body(client, catalog)
    result = preview(client, headers, body)
    identity = result["items"][0]["id"]
    body["recent_edits"] = [{"operation_id": "undo-1", "kind": "undo", "suggestion_id": identity}]
    assert not preview(client, headers, body)["items"]
    body["recent_edits"] = []
    body["active_cell"]["formula_fields"] = ["quantity"]
    item = preview(client, headers, body)["items"][0]
    assert not item["applicable"]
    assert any("公式" in issue for issue in item["issues"] if isinstance(issue, str))


def sync_body(body):
    return {
        k: v
        for k, v in body.items()
        if k
        not in {
            "local_revision",
            "query",
            "scope",
            "active_cell",
            "target_cells",
            "recent_edits",
            "intent",
        }
    }


def test_complete_local_sequence_syncs_once_and_stops_when_satisfied(client, catalog):
    headers, body = completion_body(client, catalog)
    first = preview(client, headers, body)["items"][0]
    body = accept(body, first)
    second = preview(client, headers, body)["items"][0]
    assert second["applicable"], second["issues"]
    body = accept(body, second)
    result = preview(client, headers, body)
    assert not result["items"], result["items"]
    request = sync_body(body)
    result = client.post("/api/wps/sync/preview", headers=headers, json=request)
    assert result.status_code == 200, result.text
    commit = {
        **request,
        "preview_fingerprint": result.json()["preview_fingerprint"],
        "operation_id": str(uuid4()),
    }
    first = client.post("/api/wps/sync/commit", headers=headers, json=commit)
    second = client.post("/api/wps/sync/commit", headers=headers, json=commit)
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    context = client.get(f"/api/wps/bindings/{body['binding_id']}/context", headers=headers).json()
    config = context["configuration"]
    assert len(config["devices"]) == 2
    assert len(config["accessory_allocations"]) == 1
    assert all(r["device_id"] or r["allocations"] for r in config["requirements"])


def test_existing_hardware_is_offered_for_reuse_without_new_purchase(client, catalog):
    headers, body = completion_body(client, catalog, accessory=False)
    variant = catalog["variants"][0]
    identity = str(uuid5(NAMESPACE_URL, f"presales-wps-device:{body['binding_id']}:stock"))
    body["lines"] = [
        {
            "line_id": "stock",
            "sheet": "报价表",
            "row": 5,
            "device_id": identity,
            "variant_id": variant["id"],
            "source_id": catalog["sources"][0]["id"],
            "kind": "hardware",
            "quantity": "3",
        }
    ]
    body["target_cells"].append(
        {"sheet": "报价表", "row": 5, "column": 2, "values": {"quantity": "3"}}
    )
    body["business_operations"].append(
        {
            "action": "supply_set",
            "device_id": identity,
            "allocations": [
                {
                    "id": "stock",
                    "device_id": identity,
                    "quantity": "3",
                    "source": "existing",
                    "evidence": "确认现有设备",
                }
            ],
        }
    )
    result = preview(client, headers, body)
    item = result["items"][0]
    assert item["applicable"], item["issues"]
    assert not item["line_bindings"]
    assert not any(c["kind"] == "devices" for c in item["changes"])
    assert any(
        op["action"] == "requirement_put" and op["value"].get("device_id") == identity
        for op in item["business_operations"]
    )
    assert not any(op["action"] == "supply_set" for op in item["business_operations"])

    fulfilled = accept(body, item)
    continued = preview(client, headers, fulfilled)
    assert not continued["items"], continued["items"]
    assert len(continued["configuration"]["devices"]) == 1
    assert continued["configuration"]["supply_allocations"][0]["source"] == "existing"


def test_room_role_and_active_range_are_separate_identities(client, catalog):
    headers, body = completion_body(client, catalog)
    other = deepcopy(body["business_operations"][0])
    other["new_room"]["id"] = "other-room"
    other["system"].update(id="other-system", room_id="other-room")
    body["business_operations"].append(other)
    result = preview(client, headers, body)
    assert all(
        op["value"]["system_id"] == "system"
        for op in result["items"][0]["business_operations"]
        if op["action"] == "requirement_put"
    )
    body["active_cell"]["row"] = 90
    assert client.post("/api/wps/completion/preview", headers=headers, json=body).status_code == 422


def test_removing_unsynced_product_clears_only_managed_fields(client, catalog):
    headers, body = completion_body(client, catalog)
    item = preview(client, headers, body)["items"][0]
    body = accept(body, item)
    body["active_cell"] = dict(
        sheet="报价表",
        row=3,
        column=2,
        values=item["line_bindings"][0]["confirmed_values"] | {"note": "保留备注", "price": "88"},
    )
    body["intent"] = "remove"
    removal = preview(client, headers, body)["items"][0]
    assert removal["applicable"], removal["issues"]
    assert removal["acceptance"] == "preview"
    assert removal["removed_lines"]
    assert all(p["field"] not in {"note", "quantity", "section"} for p in removal["patches"])
    assert all(p["after"] == "" for p in removal["patches"])
    body["lines"] = []
    body["removed_lines"] = removal["removed_lines"]
    body["business_operations"].extend(removal["business_operations"])
    response = client.post("/api/wps/sync/preview", headers=headers, json=sync_body(body))
    assert response.status_code == 200, response.text
    assert not any(c["kind"] == "devices" and c["after"] for c in response.json()["changes"])


def test_explicit_candidate_choice_resolves_missing_ranking_without_guessing(client, catalog):
    headers, body = completion_body(client, catalog, accessory=False, ranked=False)
    result = preview(client, headers, body)
    assert len(result["items"]) >= 2
    assert all(not item["applicable"] for item in result["items"])
    selected = result["items"][0]["line_bindings"][0]
    body.update(
        selected_variant_id=selected["variant_id"], selected_source_id=selected["source_id"]
    )
    chosen = preview(client, headers, body)
    assert len(chosen["items"]) == 1
    assert chosen["items"][0]["applicable"], chosen["items"][0]["issues"]


def test_next_edit_keeps_user_price_for_unchanged_identity(client, catalog):
    headers, body = completion_body(client, catalog, accessory=False)
    body = accept(body, preview(client, headers, body)["items"][0])
    body["active_cell"] = dict(
        sheet="报价表",
        row=3,
        column=2,
        values={
            **{
                key: str(value)
                for key, value in body["lines"][0].items()
                if key in {"model", "name", "quantity"}
            },
            "price": "88",
        },
    )
    body["lines"][0]["quantity"] = "2"
    body["lines"][0]["price"] = "88"
    body["active_cell"]["values"]["quantity"] = "2"
    result = preview(client, headers, body)
    item = result["items"][0]
    assert item["line_bindings"][0]["confirmed_values"]["price"] == "88"
    assert all(p["field"] != "price" for p in item["patches"])
    assert item["applicable"], item["issues"]
    assert any(p["field"] == "quantity" and p["after"] == "3" for p in item["patches"])


def test_confirmed_software_role_requires_its_hardware_not_catalog_adjacency(client, catalog):
    headers, body = completion_body(client, catalog, output_kind="software")
    software = preview(client, headers, body)["items"][0]
    assert software["line_bindings"][0]["kind"] == "software"
    body = accept(body, software)
    hardware = preview(client, headers, body)["items"][0]
    assert hardware["line_bindings"][0]["kind"] == "hardware"
    assert hardware["line_bindings"][0]["variant_id"] == catalog["variants"][1]["id"]
    assert any(op["action"] == "accessory_link" for op in hardware["business_operations"])


def test_zen_combination_is_the_next_incremental_edit_after_trigger(client, catalog):
    headers, body = combination_completion_body(client, catalog)
    terminal = preview(client, headers, body)["items"][0]
    assert terminal["applicable"], terminal["issues"]
    body = accept(body, terminal)

    result = preview(client, headers, body)

    assert result["items"]
    addon = result["items"][0]
    assert addon["line_bindings"][0]["variant_id"] == catalog["variants"][1]["id"]
    assert any(e.get("planning_origin") == "zen_combination" for e in addon["evidence"])
    assert any(c["kind"] == "requirements" for c in addon["changes"])
    completed = preview(client, headers, accept(body, addon))
    assert not completed["items"]


def test_only_confirmed_generatable_combinations_are_deferred_to_the_next_tab():
    base = {"kind": "combination", "code": "combination_require_all"}
    assert deferred_combination({**base, "status": "conflict", "generation_enabled": True})
    assert not deferred_combination({**base, "status": "unknown", "generation_enabled": False})
    assert not deferred_combination(
        {**base, "code": "combination_exclude", "status": "conflict", "generation_enabled": True}
    )


def test_explicit_variant_selects_one_require_any_branch():
    groups = [
        {"state": "fail", "target": {"variant_ids": ["a"]}},
        {"state": "fail", "target": {"variant_ids": ["b"]}},
    ]
    check = {"code": "combination_require_any", "groups": groups}
    assert selected_groups(check) == groups
    assert selected_groups(check, variant_id="b") == [groups[1]]


def test_replacement_cannot_carry_an_unmanaged_old_price_into_new_identity(client, catalog):
    headers, body = completion_body(client, catalog, accessory=False)
    first = preview(client, headers, body)["items"][0]
    body = accept(body, first)
    binding = first["line_bindings"][0]
    body["active_cell"] = dict(
        sheet="报价表",
        row=3,
        column=2,
        values={**binding["confirmed_values"], "price": "88"},
    )
    body["lines"][0]["price"] = "88"
    body["scope"]["requirement_id"] = binding["requirement_id"]
    body["query"] = "SERVER"
    body["selected_variant_id"] = catalog["variants"][1]["id"]
    body["selected_source_id"] = catalog["sources"][1]["id"]
    result = preview(client, headers, body)
    assert result["items"], result
    item = result["items"][0]
    assert not item["applicable"]
    assert any("旧单价不受插件管理" in i for i in item["issues"] if isinstance(i, str))
    assert not any(p["field"] == "price" for p in item["patches"])
