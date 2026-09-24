from .conftest import AUTHOR, BASE, post


def legacy_rule(client, catalog, *, mode="per_unit"):
    response = client.post(
        "/api/rules",
        json=dict(
            name="待迁移配套",
            source_product_id=catalog["sources"][0]["id"],
            target_product_id=catalog["sources"][1]["id"],
            relation="required",
            mode=mode,
            factor="2",
            status="draft",
            **AUTHOR,
        ),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_incomplete_accessory_draft_exposes_missing_fields(client, catalog):
    draft = post(
        client,
        "/knowledge",
        dict(
            name="已知需要会议主机，型号数量待确认",
            kind="accessory",
            status="draft",
            selector={"variant_ids": [catalog["variants"][0]["id"]]},
            target_variant_ids=[],
            calculation_scope=None,
            mode=None,
            factor=None,
            **AUTHOR,
        ),
    )
    assert draft["completion"] == "incomplete"
    assert draft["missing_fields"] == ["候选配置", "计算范围", "数量公式"]
    generated = {"id", "revision", "updated_at", "completion", "missing_fields"}
    confirmed = {k: v for k, v in draft.items() if k not in generated}
    confirmed["status"] = "confirmed"
    response = client.post(BASE + "/knowledge", json=confirmed)
    assert response.status_code == 422
    assert "候选配置" in response.text


def test_legacy_migration_is_idempotent_and_keeps_drafts(client, catalog):
    rules = [legacy_rule(client, catalog, mode=mode) for mode in ("per_unit", "per_group")]
    preview = client.get(BASE + "/knowledge/migration-preview").json()
    assert len(preview) == 2
    group = next(item for item in preview if item["legacy_rule"]["id"] == rules[1]["id"])
    assert group["knowledge"]["calculation_scope"] is None
    assert "旧“每组”需要确认" in group["unresolved"][0]
    first = post(client, "/knowledge/migration-apply", {"rule_ids": []})
    assert [item["action"] for item in first] == ["created", "created"]
    assert all(item["saved"]["status"] == "draft" for item in first)
    repeated = post(client, "/knowledge/migration-apply", {"rule_ids": []})
    assert [item["action"] for item in repeated] == ["unchanged", "unchanged"]


def test_migrated_legacy_update_writes_unified_knowledge(client, catalog):
    rule = legacy_rule(client, catalog)
    post(client, "/knowledge/migration-apply", {"rule_ids": [rule["id"]]})
    payload = {
        k: rule[k]
        for k in (
            "name",
            "source_product_id",
            "source_selector",
            "additional_source_ids",
            "target_product_id",
            "alternative_target_ids",
            "relation",
            "mode",
            "factor",
            "status",
            "evidence",
            "actor",
        )
    }
    payload.update(expected_revision=1, factor="3")
    response = client.put("/api/rules/" + rule["id"], json=payload)
    assert response.status_code == 200, response.text
    migrated = next(
        item
        for item in client.get(BASE + "/knowledge").json()
        if (item.get("migration_source") or {}).get("legacy_rule_id") == rule["id"]
    )
    assert migrated["factor"] == "3"
    assert migrated["migration_source"]["legacy_rule_revision"] == 2
