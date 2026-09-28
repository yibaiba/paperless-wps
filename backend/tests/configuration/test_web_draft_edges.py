from copy import deepcopy
from uuid import uuid4

from .test_list_mcp import call, mutation, saved_project
from .test_web_drafts import start, write


def read(client, draft):
    return client.get("/api/work-drafts/" + draft["id"]).json()


def test_preview_delta_does_not_change_draft_and_stale_preview_rejected(client, catalog):
    draft = start(client, saved_project(client, catalog))
    request = dict(
        expected_revision=1,
        draft_version=9,
        operations=[dict(action="device_patch", device_id="server", note="preview")],
    )
    result = client.post("/api/work-drafts/" + draft["id"] + "/preview", json=request)
    assert result.status_code == 200, result.text
    assert result.json()["draft_version"] == 9
    assert "knowledge_snapshot" not in result.text
    assert read(client, draft)["revision"] == 1
    write(client, draft, request["operations"])
    assert (
        client.post("/api/work-drafts/" + draft["id"] + "/preview", json=request).status_code == 409
    )


def test_scope_and_formal_baseline_not_rolled_back_by_undo(client, catalog):
    draft = start(client, saved_project(client, catalog))
    write(client, draft, [dict(action="device_patch", device_id="server", note="saved edit")])
    checked = call(client, "list_check", mutation(read(client, draft)))
    saved = call(
        client,
        "list_save",
        mutation(checked, expected_project_revision=1, fingerprint=checked["check_fingerprint"]),
    )
    current = read(client, draft)
    restore = dict(
        draft_id=draft["id"],
        expected_revision=current["revision"],
        checkpoint_revision=1,
        operation_id=str(uuid4()),
    )
    assert client.post("/api/work-drafts/wrong-id/restore", json=restore).status_code == 422
    result = client.post("/api/work-drafts/" + draft["id"] + "/restore", json=restore)
    assert result.status_code == 200, result.text
    assert result.json()["base_revision"] == saved["project_revision"] == 2
    assert result.json()["configuration"]["devices"][0]["note"] == ""
    assert (
        client.get("/api/configuration/projects/" + saved["project_id"]).json()["configuration"][
            "devices"
        ][0]["note"]
        == "saved edit"
    )


def test_web_and_mcp_projection_paths_match_and_supply_checks_recompute(client, catalog):
    saved = saved_project(client, catalog)
    draft = start(client, saved)
    agent = call(
        client,
        "list_create",
        dict(
            project_id=saved["project_id"],
            revision=1,
            name="隔离 Agent",
            actor="测试",
            evidence="隔离",
            operation_id=str(uuid4()),
        ),
    )
    operations = [
        dict(action="purchase_set", device_id="server", quantity="3.5", evidence="试验"),
        dict(action="description_set", device_id="server", text="项目说明"),
    ]
    response = write(client, draft, operations)
    assert response.status_code == 200, response.text
    updated = call(client, "list_update", mutation(agent, operations=operations))
    web = read(client, draft)
    agent_data = read(client, updated)
    assert web["checked"]["quotation_output"] == agent_data["checked"]["quotation_output"]
    assert any(
        c["kind"] == "supply" and c["status"] == "conflict" and c["action"]["type"] == "edit_supply"
        for c in web["checked"]["checks"]
    )


def test_tampered_snapshot_not_accepted_by_operations(client, catalog):
    draft = start(client, saved_project(client, catalog))
    value = deepcopy(draft["configuration"]["devices"][0])
    value["source_snapshot"]["prices"] = {"tampered": "0"}
    assert write(client, draft, [dict(action="device_put", value=value)]).status_code == 422
    assert read(client, draft)["revision"] == 1


def test_refresh_uses_latest_catalog_only_when_requested(client, catalog):
    saved = saved_project(client, catalog)
    draft = start(client, saved)
    identity = draft["configuration"]["devices"][0]["variant_id"]
    variant = next(
        v for v in client.get("/api/configuration/variants").json() if v["id"] == identity
    )
    from presales.configuration.catalog.schemas import VariantInput

    payload = {k: v for k, v in variant.items() if k in VariantInput.model_fields}
    payload["name"] += " 新版"
    updated = client.put(
        "/api/configuration/variants/" + identity,
        json=dict(expected_revision=variant["revision"], payload=payload),
    )
    assert updated.status_code == 200, updated.text
    old_revision = draft["configuration"]["devices"][0]["variant_snapshot"]["revision"]
    write(client, draft, [dict(action="device_patch", device_id="server", note="只改备注")])
    current = read(client, draft)
    assert current["configuration"]["devices"][0]["variant_snapshot"]["revision"] == old_revision
    response = write(client, current, [dict(action="knowledge_refresh")])
    assert response.status_code == 200, response.text
    assert (
        read(client, draft)["configuration"]["devices"][0]["variant_snapshot"]["revision"]
        == old_revision + 1
    )


def test_lightweight_projection_equals_full_check(client, catalog):
    draft = start(client, saved_project(client, catalog))
    operations = [
        dict(action="device_patch", device_id="server", note="一致性"),
        dict(action="purchase_set", device_id="server", quantity="1.5", evidence="隔离"),
        dict(action="description_set", device_id="server", text="项目参数"),
    ]
    assert write(client, draft, operations).status_code == 200
    current = read(client, draft)
    full = client.post(
        "/api/configuration/check", json=dict(configuration=current["configuration"])
    ).json()
    for key in (
        "quotation_output",
        "project_output",
        "readiness",
        "fingerprint",
        "checks",
        "device_usages",
    ):
        assert current["checked"][key] == full[key], key


def test_layout_only_does_not_recalculate_procurement(client, catalog, monkeypatch):
    draft = start(client, saved_project(client, catalog))
    from presales.configuration.projects.services import incremental
    monkeypatch.setattr(incremental, 'supply_projection', lambda *_: (_ for _ in ()).throw(AssertionError('supply recalculated')))
    monkeypatch.setattr(incremental, 'with_quotation', lambda *_: (_ for _ in ()).throw(AssertionError('quote recalculated')))
    result = write(client, draft, [dict(action='drawing_set',xml=draft['configuration']['drawing_xml'])])
    assert result.status_code == 200, result.text
