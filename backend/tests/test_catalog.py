import pytest

from presales.catalog.parser import parse_catalog


def test_configurations_and_merged_evidence_are_preserved(workbook):
    result = parse_catalog(workbook)
    assert len(result.products) == 2
    assert {p.specification for p in result.products} == {"64GB", "128GB"}
    assert all(p.hidden for p in result.products)
    assert all(p.sources["note"] == "D2:D3" for p in result.products)
    assert all(p.note == "需要核对部署容量" for p in result.products)
    assert result.products[1].prices["甲方指导价"] == "按项目申请"
    assert result.products[1].sources["price:甲方指导价"] == "E2:F3"
    assert len(result.issues) == 1
    assert result.issues[0].kind == "configuration_difference"
    assert {e["range"] for e in result.issues[0].evidence} == {"C2", "C3"}


def test_invalid_workbook_has_explicit_error():
    with pytest.raises(ValueError, match="无法读取工作簿"):
        parse_catalog(b"invalid workbook")


def test_import_is_idempotent_and_invalid_file_does_not_persist(client, workbook):
    first = client.post("/api/imports", files={"file": ("products.xlsx", workbook)})
    assert first.status_code == 200
    duplicate = client.post("/api/imports", files={"file": ("renamed.xlsx", workbook)})
    assert duplicate.json()["already_imported"] is True
    assert duplicate.json()["id"] == first.json()["id"]
    invalid = client.post("/api/imports", files={"file": ("broken.xlsx", b"broken")})
    assert invalid.status_code == 422
    assert len(client.get("/api/imports").json()) == 1
    records = client.get("/api/products", params={"import_id": first.json()["id"]}).json()
    assert len(records) == 2
    detail = client.get(f"/api/products/{records[1]['id']}").json()
    assert detail["specification"] == "128GB"
