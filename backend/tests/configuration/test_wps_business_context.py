from uuid import uuid4

from sqlalchemy import select

from presales.configuration.models import Entity

from .test_wps_addin import authorized, binding, paired, sync_body, template


def setup_workbook(client, catalog):
    token, _ = paired(client)
    headers = authorized(token)
    profile = template(client, headers, catalog)
    bound = binding(client, headers, profile)
    body = dict(
        sync_body(bound, profile, catalog),
        schema_version=2,
        expected_binding_revision=bound["binding_revision"],
    )
    return headers, profile, bound, body


def entity_versions(client):
    with client.app.state.session_factory() as session:
        return {row.id: row.revision for row in session.scalars(select(Entity))}


def test_context_requires_token_and_reads_fixed_baseline_without_writes(client, catalog):
    headers, _, bound, _ = setup_workbook(client, catalog)
    url = f"/api/wps/bindings/{bound['binding_id']}/context"
    before = entity_versions(client)
    assert client.get(url).status_code == 401
    response = client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["versions"]["catalog_snapshot_id"]
    assert response.json()["configuration"]["devices"] == []
    assert entity_versions(client) == before


def test_v2_preview_keeps_software_and_unknown_supply_without_saving(client, catalog):
    headers, _, _, body = setup_workbook(client, catalog)
    body["lines"][0]["kind"] = "software"
    before = entity_versions(client)
    response = client.post("/api/wps/sync/preview", headers=headers, json=body)
    assert response.status_code == 200, response.text
    changes = response.json()["changes"]
    assert any(
        c["after"].get("kind") == "software" for c in changes if isinstance(c["after"], dict)
    )
    assert not any(
        c["after"].get("source") == "purchase" for c in changes if isinstance(c["after"], dict)
    )
    assert entity_versions(client) == before


def test_v2_existing_supply_survives_an_unchanged_sync(client, catalog):
    headers, _, bound, body = setup_workbook(client, catalog)
    preview = client.post("/api/wps/sync/preview", headers=headers, json=body).json()
    device = preview["line_bindings"][0]["device_id"]
    body["business_operations"] = [
        {
            "action": "supply_set",
            "device_id": device,
            "allocations": [
                {
                    "id": "stock",
                    "device_id": device,
                    "quantity": "2",
                    "source": "existing",
                    "evidence": "隔离测试已有库存",
                }
            ],
        }
    ]
    preview = client.post("/api/wps/sync/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    committed = client.post(
        "/api/wps/sync/commit",
        headers=headers,
        json={
            **body,
            "preview_fingerprint": preview.json()["preview_fingerprint"],
            "operation_id": str(uuid4()),
        },
    )
    assert committed.status_code == 200, committed.text
    result = committed.json()
    body.update(
        expected_binding_revision=result["binding_revision"],
        expected_draft_revision=result["draft_revision"],
        expected_project_revision=result["base_revision"],
        known_device_ids=[device],
        business_operations=[],
    )
    body["lines"][0]["device_id"] = device
    response = client.post("/api/wps/sync/preview", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["has_changes"] is False
    context = client.get(f"/api/wps/bindings/{bound['binding_id']}/context", headers=headers).json()
    assert context["configuration"]["supply_allocations"][0]["source"] == "existing"
    legacy = {
        k: v
        for k, v in body.items()
        if k not in ("schema_version", "expected_binding_revision", "business_operations")
    }
    assert client.post("/api/wps/sync/preview", headers=headers, json=legacy).status_code == 409


def test_v2_rejects_missing_type_stale_binding_and_knowledge_refresh(client, catalog):
    headers, _, _, body = setup_workbook(client, catalog)
    body["lines"][0].pop("kind")
    assert client.post("/api/wps/sync/preview", headers=headers, json=body).status_code == 422
    body["lines"][0]["kind"] = "license"
    body["expected_binding_revision"] += 1
    assert client.post("/api/wps/sync/preview", headers=headers, json=body).status_code == 409
    body["expected_binding_revision"] -= 1
    body["business_operations"] = [{"action": "knowledge_refresh", "upgrade": True}]
    assert client.post("/api/wps/sync/preview", headers=headers, json=body).status_code == 422
