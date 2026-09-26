from .conftest import AUTHOR, BASE, post


def test_full_coverage_and_same_model_separate_configs(client, catalog):
    audit = client.get(BASE + "/audit/" + catalog["imported"]["id"]).json()
    assert audit["total"] == audit["organized"] == 2
    assert audit["pending"] == 0
    assert len({r["variant_id"] for r in audit["rows"]}) == 2
    assert all(r["duplicate_model"] for r in audit["rows"])
    assert {r["specification"] for r in audit["rows"]} == {"64GB", "128GB"}


def test_source_link_conflict_rolls_back_batch(client, catalog):
    sources, variants = catalog["sources"], catalog["variants"]
    response = client.post(
        BASE + "/source-links",
        json=dict(
            variant_id=variants[0]["id"],
            items=[
                dict(source_id=sources[1]["id"], expected_revision=1),
                dict(source_id=sources[0]["id"], expected_revision=0),
            ],
            **AUTHOR,
        ),
    )
    assert response.status_code == 409
    audit = client.get(BASE + "/audit/" + catalog["imported"]["id"]).json()
    assert all(r["link_revision"] == 1 for r in audit["rows"])
    assert len(client.get(BASE + "/source-history/" + sources[0]["id"]).json()) == 1


def test_revision_and_invalid_units(client, catalog):
    variant = catalog["variants"][0]
    payload = {k: v for k, v in variant.items() if k not in {"id", "revision", "updated_at"}}
    payload["name"] = "已核对内存"
    url = BASE + "/variants/" + variant["id"]
    change = dict(expected_revision=1, payload=payload)
    assert client.put(url, json=change).status_code == 200
    assert client.put(url, json=change).status_code == 409
    history = client.get(BASE + "/history/" + variant["id"]).json()
    assert [r["revision"] for r in history] == [2, 1]
    payload["attributes"][0]["unit"] = "随意单位"
    assert client.post(BASE + "/variants", json=payload).status_code == 422


def test_missing_source_and_draft_cannot_be_confirmed_link(client, catalog):
    v = post(
        client, "/variants", dict(product_id=catalog["product"]["id"], name="未知配置", **AUTHOR)
    )
    response = client.post(
        BASE + "/source-links",
        json=dict(
            variant_id=v["id"],
            items=[dict(source_id=catalog["sources"][0]["id"], expected_revision=1)],
            **AUTHOR,
        ),
    )
    assert response.status_code == 422


def test_bulk_independent_sources_and_conflicting_sources(client, workbook):
    imported = client.post("/api/imports", files={"file": ("bulk.xlsx", workbook)}).json()
    sources = client.get("/api/products", params={"import_id": imported["id"]}).json()
    attributes = client.put(
        "/api/products/" + sources[0]["id"] + "/attributes",
        json=dict(expected_revision=0, values={"series": ["已有测试系列"]}, **AUTHOR),
    )
    assert attributes.status_code == 200
    items = [dict(source_id=s["id"], expected_revision=0) for s in sources]
    result = post(client, "/independent-sources", dict(items=items, **AUTHOR))
    assert len({i["product_id"] for i in result["items"]}) == 2
    assert client.get(BASE + "/audit/" + imported["id"]).json()["organized"] == 2
    assert (
        client.post(BASE + "/independent-sources", json=dict(items=items, **AUTHOR)).status_code
        == 409
    )
    assert len(client.get(BASE + "/products").json()) == 2
    variant_id = result["items"][0]["variant_id"]
    post(
        client,
        "/source-links",
        dict(
            variant_id=variant_id,
            items=[dict(source_id=s["id"], expected_revision=1) for s in sources],
            **AUTHOR,
        ),
    )
    variant = next(v for v in client.get(BASE + "/variants").json() if v["id"] == variant_id)
    assert "specification" in variant["source_differences"]
    tagged = next(v for v in client.get(BASE + "/variants").json() if v["series"])
    assert tagged["series"] == ["已有测试系列"] and "沿用来源属性 v1" in tagged["evidence"]
    assert len(variant["source_details"]) == 2


def test_audit_suggests_same_model_variant_and_explains_differences(client, workbook):
    imported = client.post("/api/imports", files={"file": ("matching.xlsx", workbook)}).json()
    sources = client.get("/api/products", params={"import_id": imported["id"]}).json()
    product = post(
        client,
        "/products",
        dict(name="测试服务器", model="SERVER-X", category="服务器", **AUTHOR),
    )
    variant = post(
        client,
        "/variants",
        dict(
            product_id=product["id"],
            name="64GB 配置",
            status="confirmed",
            **AUTHOR,
        ),
    )
    post(
        client,
        "/source-links",
        dict(
            variant_id=variant["id"],
            items=[dict(source_id=sources[0]["id"], expected_revision=0)],
            **AUTHOR,
        ),
    )

    audit = client.get(BASE + "/audit/" + imported["id"]).json()
    pending = next(row for row in audit["rows"] if not row["organized"])
    suggestion = pending["match_suggestions"][0]
    assert suggestion["variant_id"] == variant["id"]
    assert suggestion["match_type"] == "conflict"
    assert "specification" in suggestion["differences"]
    assert suggestion["best_source"]["row"] == 2
