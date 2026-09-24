def setup_project(client, workbook):
    imported = client.post("/api/imports", files={"file": ("products.xlsx", workbook)}).json()
    products = client.get("/api/products", params={"import_id": imported["id"]}).json()
    project = client.post("/api/projects", json={"name": "会议室配置"}).json()
    return project, products


def test_project_keeps_specific_configuration_and_separate_rows(client, workbook):
    project, products = setup_project(client, workbook)
    path = f"/api/projects/{project['id']}/items"
    for product in products:
        response = client.post(
            path,
            json={
                "product_id": product["id"],
                "quantity": "2.5",
                "group_name": "会议室一",
                "note": "验证来源配置",
            },
        )
        assert response.status_code == 200
    items = client.get(f"/api/projects/{project['id']}").json()["items"]
    assert len(items) == 2
    assert {i["snapshot"]["specification"] for i in items} == {"64GB", "128GB"}
    updated = client.patch(
        f"{path}/{items[0]['id']}",
        json={
            "quantity": "3.25",
            "group_name": "会议室二",
            "note": "调整数量",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["quantity"] == "3.25"
    assert updated.json()["snapshot"] == items[0]["snapshot"]
    assert client.delete(f"{path}/{items[0]['id']}").status_code == 204
    assert len(client.get(f"/api/projects/{project['id']}").json()["items"]) == 1


def test_invalid_quantity_and_wrong_project_are_rejected(client, workbook):
    project, products = setup_project(client, workbook)
    path = f"/api/projects/{project['id']}/items"
    data = {"product_id": products[0]["id"], "quantity": "0", "group_name": "会议室"}
    assert client.post(path, json=data).status_code == 422
    assert client.post(path, json={**data, "quantity": "NaN"}).status_code == 422
    item = client.post(path, json={**data, "quantity": "1"}).json()
    other = client.post("/api/projects", json={"name": "另一项目"}).json()
    wrong_path = f"/api/projects/{other['id']}/items/{item['id']}"
    assert client.delete(wrong_path).status_code == 404
    assert (
        client.patch(
            wrong_path,
            json={
                "quantity": "4",
                "group_name": "另一区域",
                "note": "",
            },
        ).status_code
        == 404
    )
    assert len(client.get(f"/api/projects/{project['id']}").json()["items"]) == 1
