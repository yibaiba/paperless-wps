from io import BytesIO
from zipfile import ZipFile

import pytest

from presales.rules.selector import matches


@pytest.fixture
def attribute_setup(client, workbook):
    stream = BytesIO()
    with ZipFile(BytesIO(workbook)) as original, ZipFile(stream, "w") as archive:
        for name in original.namelist():
            content = original.read(name)
            if name.endswith("sheet1.xml"):
                content = content.replace(
                    b'<c r="A3"',
                    b'<c r="G3" t="inlineStr"><is><t>\xe5\x8f\xb0</t></is></c><c r="A3"',
                )
                row = (
                    '<row r="4">'
                    + "".join(
                        f'<c r="{col}4" t="inlineStr"><is><t>{value}</t></is></c>'
                        for col, value in {
                            "A": "HOST",
                            "B": "配套主机",
                            "C": "测试主机",
                            "G": "台",
                        }.items()
                    )
                    + "</row>"
                )
                content = content.replace(b"</sheetData>", row.encode() + b"</sheetData>")
            archive.writestr(name, content)
    content = stream.getvalue()
    response = client.post("/api/imports", files={"file": ("attributes.xlsx", content)})
    response.raise_for_status()
    imported = response.json()
    products = client.get("/api/products", params={"import_id": imported["id"]}).json()
    products.sort(key=lambda p: p["row"])
    project = client.post("/api/projects", json={"name": "属性规则验收"}).json()
    return {
        "import": imported["id"],
        "products": products,
        "path": f"/api/projects/{project['id']}",
        "content": content,
    }


def set_attributes(client, product, *, revision=0, functions=None, series=None):
    return client.put(
        f"/api/products/{product['id']}/attributes",
        json={
            "values": {"series": series or ["S系列"], "functions": functions or ["话筒升降"]},
            "expected_revision": revision,
            "actor": "测试维护人",
            "evidence": "仅测试用的配置事实",
        },
    )


def make_rule(client, setup, *, exclusions=None):
    response = client.post(
        "/api/rules",
        json={
            "name": "S系列配主机",
            "source_selector": {
                "import_id": setup["import"],
                "conditions": [
                    {"field": "series", "operator": "all", "values": ["S系列"]},
                    {"field": "functions", "operator": "all", "values": ["话筒升降"]},
                ],
                "exclude_product_ids": exclusions or [],
            },
            "target_product_id": setup["products"][2]["id"],
            "mode": "per_capacity",
            "factor": "50",
            "relation": "required",
            "status": "active",
            "actor": "测试",
            "evidence": "测试属性匹配",
        },
    )
    response.raise_for_status()
    return response.json()


def add_items(client, setup):
    for product in setup["products"][:2]:
        client.post(
            setup["path"] + "/items",
            json={"product_id": product["id"], "quantity": "30", "group_name": "系统 A"},
        ).raise_for_status()


def test_attributes_versions_and_original_source_unchanged(client, attribute_setup):
    p = attribute_setup["products"][0]
    original = client.get(f"/api/products/{p['id']}").json()
    assert set_attributes(client, p).status_code == 200
    assert set_attributes(client, p).status_code == 409
    assert set_attributes(client, p, revision=1, functions=["普通升降"]).status_code == 200
    updated = client.get(f"/api/products/{p['id']}").json()
    assert updated["specification"] == original["specification"]
    assert updated["note"] == original["note"]
    assert updated["attribute_profile"]["revision"] == 2
    history = client.get(f"/api/products/{p['id']}/attributes/history").json()
    assert [r["revision"] for r in history] == [2, 1]
    assert history[1]["values"]["functions"] == ["话筒升降"]


def test_newly_classified_product_joins_without_rule_edit_and_invalidates_preview(
    client, attribute_setup
):
    setup = attribute_setup
    a, b, _ = setup["products"]
    set_attributes(client, a).raise_for_status()
    rule = make_rule(client, setup)
    add_items(client, setup)
    before = client.get(setup["path"] + "/rule-preview").json()
    assert before["suggestions"][0]["required"] == "1"
    set_attributes(client, b).raise_for_status()
    after = client.get(setup["path"] + "/rule-preview").json()
    assert after["suggestions"][0]["required"] == "2"
    assert (
        client.post(
            setup["path"] + "/rule-apply",
            json={
                "fingerprint": before["fingerprint"],
                "suggestion_ids": [before["suggestions"][0]["id"]],
            },
        ).status_code
        == 409
    )
    client.post(
        setup["path"] + "/rule-apply",
        json={
            "fingerprint": after["fingerprint"],
            "suggestion_ids": [after["suggestions"][0]["id"]],
        },
    ).raise_for_status()
    set_attributes(client, b, revision=1, series=["其他系列"]).raise_for_status()
    current = client.get(setup["path"] + "/rule-preview").json()
    assert current["suggestions"][0]["required"] == "1"
    history = client.get(setup["path"] + "/rule-history").json()[0]
    match = history["calculation"]["suggestions"][0]["rules"][0]
    assert len(match["sources"]) == 2 and match["attribute_snapshot"][b["id"]]["revision"] == 1
    revisions = client.get(f"/api/rules/{rule['id']}/history").json()
    assert len(revisions) == 1 and len(revisions[0]["sources"]) == 1


def test_exclusions_and_import_version_scope(client, attribute_setup):
    setup = attribute_setup
    a, b, _ = setup["products"]
    set_attributes(client, a).raise_for_status()
    set_attributes(client, b).raise_for_status()
    rule = make_rule(client, setup, exclusions=[b["id"]])
    result = client.post("/api/rules/source-preview", json=rule["source_selector"]).json()
    assert [p["id"] for p in result["products"]] == [a["id"]]
    changed = BytesIO(setup["content"])
    with ZipFile(changed, "a") as archive:
        archive.comment = b"new source version"
    imported = client.post("/api/imports", files={"file": ("new.xlsx", changed.getvalue())}).json()
    new = client.get("/api/products", params={"import_id": imported["id"]}).json()[0]
    set_attributes(client, new).raise_for_status()
    preview = client.post("/api/rules/source-preview", json=rule["source_selector"]).json()
    assert [p["id"] for p in preview["products"]] == [a["id"]]


def test_zero_matches_is_explicit_and_does_not_use_all_products(client, attribute_setup):
    rule = make_rule(client, attribute_setup)
    assert rule["sources"] == [] and rule["source"] is None
    add_items(client, attribute_setup)
    preview = client.get(attribute_setup["path"] + "/rule-preview").json()
    assert preview["suggestions"] == [] and len(preview["uncovered_items"]) == 2


def test_batch_is_atomic_and_preserves_other_fields(client, attribute_setup):
    a, b, _ = attribute_setup["products"]
    set_attributes(client, a).raise_for_status()
    items = [{"product_id": p["id"], "expected_revision": 0} for p in (b, a)]
    payload = {
        "items": items,
        "field": "interfaces",
        "values": ["RS485"],
        "operation": "add",
        "actor": "测试",
        "evidence": "测试批量维护",
    }
    assert client.post("/api/attributes/batch", json=payload).status_code == 409
    assert client.get(f"/api/products/{b['id']}").json()["attribute_profile"]["revision"] == 0
    items[1]["expected_revision"] = 1
    response = client.post("/api/attributes/batch", json=payload)
    response.raise_for_status()
    first = client.get(f"/api/products/{a['id']}").json()["attribute_profile"]
    assert first["values"]["interfaces"] == ["RS485"] and first["values"]["series"] == ["S系列"]


def test_matching_target_error_stays_editable_and_calculation_fails_explicitly(
    client, attribute_setup
):
    a, _, target = attribute_setup["products"]
    set_attributes(client, a).raise_for_status()
    rule = make_rule(client, attribute_setup)
    set_attributes(client, target).raise_for_status()
    rules = client.get("/api/rules")
    rules.raise_for_status()
    assert rules.json()[0]["matching_errors"]
    add_items(client, attribute_setup)
    response = client.get(attribute_setup["path"] + "/rule-preview")
    assert response.status_code == 422 and "自身" in response.json()["detail"]
    selector = {**rule["source_selector"], "exclude_product_ids": [target["id"]]}
    data = {
        k: rule[k]
        for k in (
            "name",
            "target_product_id",
            "mode",
            "factor",
            "relation",
            "status",
            "actor",
            "evidence",
        )
    }
    response = client.put(
        f"/api/rules/{rule['id']}",
        json={**data, "source_selector": selector, "expected_revision": 1},
    )
    response.raise_for_status()
    assert response.json()["matching_errors"] == []


@pytest.mark.parametrize("operator,expected", [("all", False), ("any", True)])
def test_attribute_operators_are_exact(operator, expected):
    assert (
        matches(
            {"functions": ["升降"]},
            [{"field": "functions", "operator": operator, "values": ["升降", "话筒"]}],
        )
        is expected
    )
    assert not matches(
        {"series": ["S系列扩展"]}, [{"field": "series", "operator": "any", "values": ["S系列"]}]
    )
