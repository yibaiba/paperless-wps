from copy import deepcopy
from uuid import NAMESPACE_URL, uuid4, uuid5

from .test_proposal_generation import published
from .test_wps_business_context import entity_versions, setup_workbook


def completion_body(client, catalog, *, quantity=True, accessory=True):
    definition, package = published(client, catalog, quantity=quantity, accessory=accessory)
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
        not in {"local_revision", "query", "scope", "active_cell", "target_cells", "recent_edits"}
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
        if op["action"] == "requirement_put" and op["value"].get("device_id")
    )
    body["active_cell"]["row"] = 90
    assert client.post("/api/wps/completion/preview", headers=headers, json=body).status_code == 422
