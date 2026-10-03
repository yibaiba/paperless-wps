from copy import deepcopy

from .conftest import BASE, knowledge, post
from .test_evolution import ready_project


def test_explicit_runtime_upgrade_preserves_product_knowledge_and_price(
    client, catalog, config, project
):
    original = post(client, "/check", dict(configuration=ready_project(client, catalog, config)))
    before = original["configuration"]
    assert before["decision_runtime"] == "python-v3"
    request = dict(configuration=before, expected_revision=0, upgrade_decisions=True)
    preview = post(client, f"/projects/{project['id']}/change-preview", request)
    upgraded = preview["checked"]
    assert upgraded["checks"] == original["checks"]
    after = upgraded["configuration"]
    assert after["decision_runtime"] == "zen-v1" and after["decision_bundle_id"]
    for key in ("devices", "quotation", "knowledge_snapshot_id", "definition_snapshot_id"):
        assert after[key] == before[key]
    assert client.get(BASE + f"/projects/{project['id']}").json()["revision"] == 0
    applied = post(
        client,
        f"/projects/{project['id']}/change-apply",
        dict(request, fingerprint=preview["fingerprint"]),
    )
    repeat = post(client, "/check", dict(configuration=applied["configuration"]))
    assert repeat["fingerprint"] == applied["fingerprint"]
    assert repeat["decision"] == applied["decision"]
    saved = client.put(
        BASE + f"/projects/{project['id']}", json=dict(expected_revision=0, configuration=after)
    )
    assert saved.status_code == 200, saved.text
    assert client.get(BASE + f"/projects/{project['id']}").json()["configuration"] == after


def test_zen_snapshot_does_not_adopt_later_knowledge(client, catalog, config):
    knowledge(client, catalog["variants"][0])
    data = dict(deepcopy(config), calculation_version=3, decision_runtime="zen-v1")
    checked = post(client, "/check", dict(configuration=data))
    knowledge(client, catalog["variants"][0], effect="deny")
    frozen = post(client, "/check", dict(configuration=checked["configuration"]))
    assert frozen["fingerprint"] == checked["fingerprint"]
    assert frozen["checks"] == checked["checks"]
    latest = post(
        client, "/check", dict(configuration=checked["configuration"], refresh_knowledge=True)
    )
    assert (
        latest["configuration"]["decision_bundle_id"]
        != checked["configuration"]["decision_bundle_id"]
    )
    assert any(c["kind"] == "compatibility" and c["status"] == "conflict" for c in latest["checks"])


def test_zen_candidate_matches_project_and_legacy(client, catalog, config):
    knowledge(client, catalog["variants"][0])
    data = dict(config, calculation_version=3, decision_runtime="zen-v1")
    checked = post(client, "/check", dict(configuration=data))
    payload = dict(
        calculation_version=3,
        decision_runtime="zen-v1",
        system="无纸化",
        role="服务端",
        knowledge_snapshot_id=checked["configuration"]["knowledge_snapshot_id"],
    )
    candidates = post(client, "/candidates", payload)
    selected = next(c for c in candidates if c["variant"]["id"] == catalog["variants"][0]["id"])
    compatibility = next(c for c in checked["checks"] if c["kind"] == "compatibility")
    assert selected["status"] == compatibility["status"]
    assert selected["evidence"] == compatibility["evidence"]
    assert candidates == post(client, "/candidates", dict(payload, decision_runtime="python-v3"))


def test_package_round_trip_cannot_override_compiled_reference(client, catalog):
    from .test_proposal_generation import published

    definition, package = published(client, catalog)
    payload = {
        k: v
        for k, v in package.items()
        if k not in {"id", "revision", "updated_at", "definition", "rules"}
    }
    payload["decision_bundle_id"] = "forged-reference"
    updated = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["decision_bundle_id"] == package["decision_bundle_id"]


def test_candidate_rejects_mismatched_snapshot_and_bundle(client, catalog, config):
    knowledge(client, catalog["variants"][0])
    old = post(
        client,
        "/check",
        dict(configuration=dict(config, calculation_version=3, decision_runtime="zen-v1")),
    )["configuration"]
    knowledge(client, catalog["variants"][0], effect="deny")
    new = post(client, "/check", dict(configuration=old, refresh_knowledge=True))["configuration"]
    payload = dict(
        calculation_version=3,
        decision_runtime="zen-v1",
        system="无纸化",
        role="服务端",
        knowledge_snapshot_id=new["knowledge_snapshot_id"],
        decision_bundle_id=old["decision_bundle_id"],
    )
    response = client.post(BASE + "/candidates", json=payload)
    assert response.status_code == 422 and "不一致" in response.text
    payload.update(configuration=old, requirement_id="r1")
    response = client.post(BASE + "/candidates", json=payload)
    assert response.status_code == 422 and "knowledge_snapshot_id" in response.text


def test_unconfigured_legacy_project_requires_explicit_runtime_upgrade(client, catalog, project):
    from presales.storage import Project

    with client.app.state.session_factory() as session:
        old = Project(name="升级前创建的项目")
        session.add(old)
        session.commit()
        identity = old.id
    legacy = client.get(BASE + "/projects/" + identity).json()
    assert legacy["configuration"]["decision_runtime"] == "python-v3"
    from .test_list_mcp import call, mutation

    response = client.post(
        "/api/work-drafts",
        json=dict(project_id=identity, expected_revision=0, operation_id=identity),
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    call(client, "list_check", mutation(draft))
    changes = call(client, "list_get", dict(draft_id=draft["id"], view="changes"))["items"]
    assert not any(c["kind"] == "decision_runtime" for c in changes)
    assert (
        client.get(BASE + "/projects/" + project["id"]).json()["configuration"]["decision_runtime"]
        == "zen-v1"
    )
    response = client.post(
        "/api/projects/" + identity + "/items",
        json=dict(product_id=catalog["sources"][0]["id"], quantity="2", group_name="旧系统"),
    )
    assert response.status_code == 200, response.text
    preview = client.get(BASE + "/projects/" + identity + "/import-preview").json()["configuration"]
    assert preview["decision_runtime"] == "python-v3"
    preview.update(actor="测试", evidence="隔离旧清单")
    saved = client.put(
        BASE + "/projects/" + identity, json=dict(expected_revision=0, configuration=preview)
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["configuration"]["decision_runtime"] == "python-v3"
    upgraded = post(
        client, "/check", dict(configuration=saved.json()["configuration"], upgrade_decisions=True)
    )
    assert upgraded["configuration"]["decision_runtime"] == "zen-v1"
