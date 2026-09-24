import pytest
import zen

from presales.rules.engine import ZenQuantityEngine


@pytest.mark.parametrize(
    "mode,quantity,factor,expected",
    [
        ("per_capacity", "20", "2", "10"),
        ("per_capacity", "21", "2", "11"),
        ("per_capacity", "0", "2", "0"),
        ("per_unit", "3", "1.5", "4.5"),
    ],
)
def test_real_zen_calculation(mode, quantity, *, factor, expected):
    engine = ZenQuantityEngine(zen.ZenEngine())
    result = engine.calculate(mode=mode, quantity=quantity, factor=factor)
    assert result["quantity"] == expected
    assert result["trace"]["calculate"]["input"]["quantity"] == quantity
    assert result["engine"] == "GoRules ZEN 0.53.0"


@pytest.fixture
def rule_setup(client, workbook):
    imported = client.post("/api/imports", files={"file": ("products.xlsx", workbook)}).json()
    products = client.get("/api/products", params={"import_id": imported["id"]}).json()
    payload = {
        "name": "每两个设备配一个附件",
        "source_product_id": products[0]["id"],
        "target_product_id": products[1]["id"],
        "mode": "per_capacity",
        "factor": "2",
        "status": "active",
        "evidence": "测试规则：一对二",
        "actor": "测试维护人",
    }
    rule = client.post("/api/rules", json=payload)
    assert rule.status_code == 200
    project = client.post("/api/projects", json={"name": "配套测试"}).json()
    return {"payload": payload, "rule": rule.json(), "project": project["id"], "products": products}


def add(client, setup, *, index=0, quantity="1", group="A"):
    response = client.post(
        f"/api/projects/{setup['project']}/items",
        json={
            "product_id": setup["products"][index]["id"],
            "quantity": quantity,
            "group_name": group,
            "note": "人工录入，不能覆盖",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_group_rounding_deduct_apply_and_reapply(client, rule_setup):
    setup = rule_setup
    original = add(client, setup, quantity="10")
    add(client, setup, quantity="11")
    add(client, setup, quantity="1", group="B")
    add(client, setup, index=1, quantity="3")
    base = f"/api/projects/{setup['project']}"
    preview = client.get(base + "/rule-preview").json()
    first, second = preview["suggestions"]
    assert (first["required"], first["existing"], first["missing"]) == ("11", "3", "8")
    assert second["missing"] == "1"
    data = {"fingerprint": preview["fingerprint"], "suggestion_ids": [first["id"], second["id"]]}
    assert client.post(base + "/rule-apply", json=data).status_code == 200
    assert client.post(base + "/rule-apply", json=data).status_code == 409
    new_preview = client.get(base + "/rule-preview").json()
    assert all(s["missing"] == "0" for s in new_preview["suggestions"])
    unchanged = next(i for i in client.get(base).json()["items"] if i["id"] == original["id"])
    assert unchanged == original
    history = client.get(base + "/rule-history").json()
    assert len(history) == 1
    assert history[0]["calculation"]["suggestions"][0]["rules"][0]["trace"]["calculate"]


def test_rule_change_invalidates_preview_and_keeps_history(client, rule_setup):
    setup = rule_setup
    add(client, setup, quantity="20")
    base = f"/api/projects/{setup['project']}"
    before = client.get(base + "/rule-preview").json()
    update = {**setup["payload"], "expected_revision": 1, "factor": "4"}
    path = f"/api/rules/{setup['rule']['id']}"
    assert client.put(path, json=update).status_code == 200
    assert client.put(path, json=update).status_code == 409
    response = client.post(
        base + "/rule-apply",
        json={
            "fingerprint": before["fingerprint"],
            "suggestion_ids": [before["suggestions"][0]["id"]],
        },
    )
    assert response.status_code == 409
    assert client.get(base + "/rule-preview").json()["suggestions"][0]["missing"] == "5"
    assert [r["factor"] for r in client.get(path + "/history").json()] == ["4", "2"]


def test_drafts_and_disabled_rules_do_not_calculate(client, rule_setup):
    setup = rule_setup
    add(client, setup, quantity="21")
    path = f"/api/rules/{setup['rule']['id']}"
    for revision, status in enumerate(("draft", "disabled"), start=1):
        response = client.put(
            path, json={**setup["payload"], "expected_revision": revision, "status": status}
        )
        assert response.status_code == 200
        preview = client.get(f"/api/projects/{setup['project']}/rule-preview").json()
        assert preview["suggestions"] == []
        assert len(preview["uncovered_items"]) == 1
        assert client.post(path + "/trial", json={"quantity": "21"}).json()["quantity"] == "11"


def test_multiple_rules_add_demand_and_excess_is_not_deleted(client, rule_setup):
    setup = rule_setup
    add(client, setup, quantity="3")
    add(client, setup, index=1, quantity="10")
    assert (
        client.post(
            "/api/rules", json={**setup["payload"], "mode": "per_unit", "factor": "1"}
        ).status_code
        == 200
    )
    preview = client.get(f"/api/projects/{setup['project']}/rule-preview").json()
    suggestion = preview["suggestions"][0]
    assert (suggestion["required"], suggestion["missing"], suggestion["surplus"]) == ("5", "0", "5")
    assert len(suggestion["rules"]) == 2


@pytest.mark.parametrize(
    "override",
    [{"factor": "0"}, {"factor": "-1"}, {"factor": "NaN"}, {"evidence": " "}, {"mode": "script"}],
)
def test_invalid_rule_is_rejected(client, rule_setup, override):
    assert client.post("/api/rules", json={**rule_setup["payload"], **override}).status_code == 422


def test_apply_rejects_fabricated_suggestions(client, rule_setup):
    base = f"/api/projects/{rule_setup['project']}"
    add(client, rule_setup)
    preview = client.get(base + "/rule-preview").json()
    for selected in [["fabricated"], [preview["suggestions"][0]["id"]] * 2]:
        response = client.post(
            base + "/rule-apply",
            json={"fingerprint": preview["fingerprint"], "suggestion_ids": selected},
        )
        assert response.status_code == 422
    assert len(client.get(base).json()["items"]) == 1
