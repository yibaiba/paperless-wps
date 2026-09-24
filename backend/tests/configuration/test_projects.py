from copy import deepcopy

from .conftest import BASE, knowledge, post


def save(client, project, config, revision=0):
    response = client.put(
        BASE + "/projects/" + project["id"],
        json=dict(expected_revision=revision, configuration=config),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["name"] == project["name"]
    return result


def test_shared_counts_and_resource_limit(client, catalog, config, project):
    config["requirements"].append(
        dict(
            id="r2",
            system_id="booking",
            role="服务端",
            device_id="device-1",
            resources=[dict(key="memory", amount="40", unit="GB")],
        )
    )
    config["devices"][0]["variant_id"] = catalog["variants"][0]["id"]
    result = save(client, project, config)
    assert len(result["configuration"]["devices"]) == 1
    items = client.get("/api/projects/" + project["id"]).json()["items"]
    assert len(items) == 1 and items[0]["quantity"] == "1"
    capacity = next(c for c in result["checks"] if c["kind"] == "capacity")
    assert capacity["required"] == "80"
    expected = "conflict" if catalog["sources"][0]["specification"] == "64GB" else "pass"
    assert capacity["status"] == expected
    assert any(c["kind"] == "sharing" and c["status"] == "unknown" for c in result["checks"])
    independent = deepcopy(result["configuration"])
    independent["devices"].append({**independent["devices"][0], "id": "device-2"})
    independent["requirements"][1]["device_id"] = "device-2"
    second = save(client, project, independent, 1)
    assert len(second["configuration"]["devices"]) == 2
    assert len(client.get("/api/projects/" + project["id"]).json()["items"]) == 2


def test_versions_pinned_and_concurrent_save(client, catalog, config, project):
    rule = knowledge(client, catalog["variants"][0])
    first = save(client, project, config)
    payload = {k: v for k, v in rule.items() if k not in {"id", "revision", "updated_at"}}
    payload["effect"] = "deny"
    assert (
        client.put(
            BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
        ).status_code
        == 200
    )
    old = post(client, "/check", dict(configuration=first["configuration"]))
    assert old["checks"][0]["status"] == "pass"
    assert old["version_changes"][0]["current"] == 2
    latest = post(
        client, "/check", dict(configuration=first["configuration"], refresh_knowledge=True)
    )
    assert latest["checks"][0]["status"] == "conflict"
    assert (
        client.put(
            BASE + "/projects/" + project["id"],
            json=dict(expected_revision=0, configuration=first["configuration"]),
        ).status_code
        == 409
    )
    assert client.get(BASE + "/projects/" + project["id"]).json()["revision"] == 1


def test_legacy_changes_write_same_configuration(client, catalog, config, project):
    save(client, project, config)
    path = "/api/projects/" + project["id"] + "/items"
    changed = client.patch(
        path + "/device-1", json=dict(quantity="2", group_name="无纸化系统", note="调整")
    )
    assert changed.status_code == 200, changed.text
    current = client.get(BASE + "/projects/" + project["id"]).json()
    assert current["configuration"]["devices"][0]["quantity"] == "2"
    assert current["revision"] == 2
    added = client.post(
        path, json=dict(product_id=catalog["sources"][1]["id"], quantity="1", group_name="扩展")
    )
    assert added.status_code == 200, added.text
    assert (
        len(client.get(BASE + "/projects/" + project["id"]).json()["configuration"]["devices"]) == 2
    )
    assert client.delete(path + "/device-1").status_code == 204
    assert (
        len(client.get(BASE + "/projects/" + project["id"]).json()["configuration"]["devices"]) == 1
    )


def test_forged_snapshot_rejected(client, catalog, config):
    result = post(client, "/check", dict(configuration=config))
    result["configuration"]["devices"][0]["variant_snapshot"]["attributes"][0]["value"] = "999999"
    response = client.post(BASE + "/check", json=dict(configuration=result["configuration"]))
    assert response.status_code == 422


def test_software_counts_separately_and_unknown_saved(client, catalog, config, project):
    config["devices"].append(
        {**config["devices"][0], "id": "license", "kind": "software", "quantity": "20"}
    )
    result = save(client, project, config)
    assert any(c["status"] == "unknown" for c in result["checks"])
    assert len(result["configuration"]["devices"]) == 2
    assert sorted(
        i["quantity"] for i in client.get("/api/projects/" + project["id"]).json()["items"]
    ) == ["1", "20"]


def test_unified_project_rejects_legacy_rule_calculation(client, catalog, config, project):
    original = save(client, project, config)
    rule = client.post(
        "/api/rules",
        json=dict(
            name="隔离旧规则",
            source_product_id=catalog["sources"][0]["id"],
            target_product_id=catalog["sources"][1]["id"],
            mode="per_unit",
            factor="2",
            status="active",
            actor="测试",
            evidence="隔离测试，无业务含义",
        ),
    )
    assert rule.status_code == 200
    path = "/api/projects/" + project["id"]
    preview = client.get(path + "/rule-preview")
    assert preview.status_code == 422
    assert "统一配置" in preview.text
    result = client.post(
        path + "/rule-apply",
        json=dict(
            fingerprint="旧入口不应继续计算",
            suggestion_ids=["旧入口不应应用"],
        ),
    )
    assert result.status_code == 422
    assert "统一配置" in result.text
    updated = client.get(BASE + "/projects/" + project["id"]).json()
    assert updated["revision"] == original["revision"]
    assert len(updated["configuration"]["devices"]) == 1
    assert len(client.get(path).json()["items"]) == 1
