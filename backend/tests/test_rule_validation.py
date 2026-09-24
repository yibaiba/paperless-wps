import pytest

from presales.rules.schemas import RuleInput


@pytest.mark.parametrize(
    "override",
    [
        {"additional_source_ids": ["source"]},
        {"additional_source_ids": ["second", "second"]},
        {"additional_source_ids": ["target"]},
        {"additional_source_ids": [""]},
        {"relation": "choice"},
        {"alternative_target_ids": ["second"]},
        {"relation": "choice", "alternative_target_ids": ["target"]},
        {"relation": "choice", "alternative_target_ids": ["source"]},
    ],
)
def test_invalid_shared_and_choice_definitions_fail_explicitly(override):
    with pytest.raises(ValueError):
        RuleInput.model_validate(
            {
                "name": "规则验证",
                "source_product_id": "source",
                "target_product_id": "target",
                "mode": "per_group",
                "factor": "1",
                "evidence": "测试",
                "actor": "测试",
                **override,
            }
        )


def test_unknown_additional_product_is_rejected(client, workbook):
    result = client.post("/api/imports", files={"file": ("products.xlsx", workbook)}).json()
    products = client.get("/api/products", params={"import_id": result["id"]}).json()
    response = client.post(
        "/api/rules",
        json={
            "name": "未知型号",
            "source_product_id": products[0]["id"],
            "additional_source_ids": ["not-a-product"],
            "target_product_id": products[1]["id"],
            "mode": "per_group",
            "factor": "1",
            "evidence": "测试",
            "actor": "测试",
        },
    )
    assert response.status_code == 422
    assert "不存在" in response.json()["detail"]
