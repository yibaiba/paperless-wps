from uuid import uuid4

from .test_list_mcp import saved_project


def start(client, saved):
    response = client.post(
        "/api/work-drafts",
        json=dict(project_id=saved["project_id"], expected_revision=1, operation_id=str(uuid4())),
    )
    assert response.status_code == 200, response.text
    return response.json()


def write(client, draft, operations, **extra):
    request = (
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            operations=operations,
        )
        | extra
    )
    return client.post("/api/work-drafts/" + draft["id"] + "/edit", json=request)


def test_restore_retry_conflict_and_formal_isolation(client, catalog):
    saved = saved_project(client, catalog)
    draft = start(client, saved)
    operation_id = str(uuid4())
    operations = [dict(action="device_patch", device_id="server", note="工作草稿")]
    first = write(client, draft, operations, operation_id=operation_id)
    assert first.status_code == 200, first.text
    assert write(client, draft, operations, operation_id=operation_id).json() == first.json()
    assert write(client, draft, operations).status_code == 409
    current = client.get("/api/work-drafts/" + draft["id"]).json()
    assert current["configuration"]["devices"][0]["note"] == "工作草稿"
    assert (
        client.get("/api/configuration/projects/" + saved["project_id"]).json()["configuration"][
            "devices"
        ][0]["note"]
        == ""
    )
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
    assert restored.json()["configuration"]["devices"][0]["note"] == ""
    assert restored.json()["revision"] == 3


def test_note_does_not_run_full_check_and_delta_has_no_snapshots(client, catalog, monkeypatch):
    draft = start(client, saved_project(client, catalog))
    from presales.configuration.projects.repository import ProjectConfigurations

    monkeypatch.setattr(
        ProjectConfigurations,
        "check",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("full check")),
    )
    response = write(client, draft, [dict(action="device_patch", device_id="server", note="备注")])
    assert response.status_code == 200, response.text
    patch = response.json()["configuration_patch"]
    assert patch["device_changes"] == [dict(id="server", note="备注")]
    assert "knowledge_snapshot" not in patch


def test_invalid_batch_atomic(client, catalog):
    draft = start(client, saved_project(client, catalog))
    response = write(
        client,
        draft,
        [
            dict(action="device_patch", device_id="server", note="不会写入"),
            dict(action="device_patch", device_id="missing", note="error"),
        ],
    )
    assert response.status_code == 422, response.text
    assert client.get("/api/work-drafts/" + draft["id"]).json()["revision"] == 1


def test_device_usage_details_are_bound_to_the_draft_revision(client, catalog):
    draft = start(client, saved_project(client, catalog))
    response = client.get(
        f"/api/work-drafts/{draft['id']}/device-usages",
        params=dict(revision=draft["revision"], device_id="server"),
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["total"] == 1
    assert detail["items"][0]["device_id"] == "server"
    write(client, draft, [dict(action="device_patch", device_id="server", note="新版")])
    stale = client.get(
        f"/api/work-drafts/{draft['id']}/device-usages",
        params=dict(revision=draft["revision"], device_id="server"),
    )
    assert stale.status_code == 409
