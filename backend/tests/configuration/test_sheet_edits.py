from copy import deepcopy

from .test_list_mcp import call, mutation, saved_project


def preview(client, saved, operations, **extra):
    project_id = saved["project_id"]
    current = client.get("/api/configuration/projects/" + project_id).json()
    return client.post(
        f"/api/configuration/projects/{project_id}/edit-preview",
        json=dict(
            configuration=current["configuration"],
            expected_revision=current["revision"],
            draft_version=7,
            operations=operations,
        )
        | extra,
    )


def test_preview_atomic_missing_id_does_not_save(client, catalog):
    saved = saved_project(client, catalog)
    operations = [
        dict(action="device_patch", device_id="server", note="未保存测试"),
        dict(action="section_set", device_id="missing", section="测试"),
    ]
    response = preview(client, saved, operations)
    assert response.status_code == 422
    assert response.json()["detail"]["operation_index"] == 1
    original = client.get("/api/configuration/projects/" + saved["project_id"]).json()
    assert original["revision"] == 1
    assert original["configuration"]["devices"][0]["note"] == ""


def test_quantity_keeps_supply_and_reports_unassigned(client, catalog):
    saved = saved_project(client, catalog)
    response = preview(
        client,
        saved,
        [dict(action="device_patch", device_id="server", quantity="3.5", note="测试增加")],
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["draft_version"] == 7
    checked = result["checked"]
    assert checked["configuration"]["devices"][0]["quantity"] == "3.5"
    line = checked["quotation_output"]["lines"][0]
    assert line["purchase_quantity"] == "2.5"
    assert line["unknown_quantity"] == "1.0"
    assert checked["quotation_output"]["total"] is None
    assert client.get("/api/configuration/projects/" + saved["project_id"]).json()["revision"] == 1


def test_web_mcp_edit_equivalence_and_save(client, catalog):
    saved = saved_project(client, catalog)
    project_id = saved["project_id"]
    initial = client.get("/api/configuration/projects/" + project_id).json()
    price = deepcopy(initial["configuration"]["quotation"]["prices"][0])
    price.update(unit_price="0", evidence="测试零价")
    operations = [
        dict(action="price_set", value=price),
        dict(action="section_set", device_id="server", section="公共设备"),
        dict(action="device_patch", device_id="server", note="测试备注"),
    ]
    web = preview(client, saved, operations).json()["checked"]
    draft = call(
        client,
        "list_create",
        dict(
            name="改单测试",
            project_id=project_id,
            revision=1,
            operation_id="sheet-copy",
            actor="测试",
            evidence="隔离测试",
        ),
    )
    draft = call(client, "list_update", mutation(draft, operations=operations))
    quote = call(client, "list_get", dict(draft_id=draft["id"], view="quotation"))
    assert web["quotation_output"]["total"] == quote["total"] == "0.00"
    assert web["quotation_output"]["lines"][0]["section"] == "公共设备"
    response = client.put(
        "/api/configuration/projects/" + project_id,
        json=dict(
            expected_revision=1,
            configuration=web["configuration"],
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2
    conflict = preview(client, saved, operations, expected_revision=1)
    assert conflict.status_code == 409


def test_invalid_numeric_input_and_readonly_snapshot(client, catalog):
    saved = saved_project(client, catalog)
    for quantity in ("", "=1+1", "-1", "NaN"):
        response = preview(
            client, saved, [dict(action="device_patch", device_id="server", quantity=quantity)]
        )
        assert response.status_code == 422
    response = preview(
        client,
        saved,
        [dict(action="device_patch", device_id="server", note="test", source_snapshot={})],
    )
    assert response.status_code == 422


def test_batch_decimal_price_zero_and_model_change_remains_stale(client, catalog):
    saved = saved_project(client, catalog)
    project_id = saved["project_id"]
    initial = client.get("/api/configuration/projects/" + project_id).json()
    price = deepcopy(initial["configuration"]["quotation"]["prices"][0])
    price.update(unit_price="0", evidence="隔离零价测试")
    operations = [
        dict(action="device_patch", device_id="server", quantity="3.75"),
        dict(action="price_set", value=price),
        dict(action="section_set", device_id="server", section="公共设备"),
        dict(action="device_patch", device_id="server", note="整批操作"),
    ]
    result = preview(client, saved, operations).json()["checked"]
    line = result["quotation_output"]["lines"][0]
    assert line["unit_price"] == "0"
    assert line["amount"] == "0.00"
    assert line["unknown_quantity"] == "1.25"
    assert result["quotation_output"]["total"] is None
    assert result["configuration"]["devices"][0]["note"] == "整批操作"
    variant, source = catalog["variants"][1], catalog["sources"][1]
    response = preview(
        client,
        saved,
        [
            dict(
                action="device_put",
                value=dict(
                    id="server",
                    name="换型测试",
                    variant_id=variant["id"],
                    source_id=source["id"],
                    quantity="2.5",
                    kind="hardware",
                ),
            )
        ],
    )
    output = response.json()["checked"]["quotation_output"]
    assert output["total"] is None
    assert any("过期" in issue for issue in output["lines"][0]["issues"])


def test_replacement_catalog_without_role_is_explicitly_unknown(client, catalog):
    response = client.post(
        "/api/configuration/candidates", json=dict(mode="all", calculation_version=3)
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == len(catalog["variants"])
    assert all(item["status"] == "unknown" for item in response.json())
    assert client.post("/api/configuration/candidates", json=dict(mode="known")).status_code == 422
