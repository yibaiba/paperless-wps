from copy import deepcopy
from xml.etree import ElementTree as ET

from .conftest import BASE, post
from .test_projects import save


def test_draw_copy_is_reference_clone_increases_bom(client, config, project):
    checked = post(client, "/check", dict(configuration=config))
    data = checked["configuration"]
    drawing = post(
        client, "/drawing", dict(devices=data["devices"], add_ids=["device-1", "device-1"])
    )
    data["drawing_xml"] = drawing["xml"]
    first = save(client, project, data)
    assert len(first["configuration"]["devices"]) == 1
    root = ET.fromstring(first["configuration"]["drawing_xml"])
    assert len(root.findall('.//*[@cfg_device_id="device-1"]')) == 2
    data["devices"].append({**data["devices"][0], "id": "cloned"})
    data["drawing_xml"] = post(
        client,
        "/drawing",
        dict(xml=data["drawing_xml"], devices=data["devices"], add_ids=["cloned"]),
    )["xml"]
    second = save(client, project, data, 1)
    assert len(second["configuration"]["devices"]) == 2
    assert len(client.get("/api/projects/" + project["id"]).json()["items"]) == 2


def test_drawing_movement_not_recalculate_and_deleted_shape_keeps_device(client, config):
    first = post(client, "/check", dict(configuration=config))
    data = deepcopy(first["configuration"])
    data["drawing_xml"] = post(
        client, "/drawing", dict(devices=data["devices"], add_ids=["device-1"])
    )["xml"]
    second = post(client, "/check", dict(configuration=data))
    assert second["fingerprint"] == first["fingerprint"]
    data["drawing_xml"] = post(
        client,
        "/drawing",
        dict(xml=data["drawing_xml"], devices=data["devices"], remove_device_id="device-1"),
    )["xml"]
    assert "cfg_device_id" not in data["drawing_xml"]
    assert len(post(client, "/check", dict(configuration=data))["configuration"]["devices"]) == 1


def test_legacy_preview_leaves_original_untouched(client, catalog, project):
    old = client.post(
        "/api/projects/" + project["id"] + "/items",
        json=dict(product_id=catalog["sources"][0]["id"], quantity="2", group_name="旧系统"),
    ).json()
    preview = client.get(BASE + "/projects/" + project["id"] + "/import-preview").json()
    assert preview["unmapped"] == []
    assert preview["configuration"]["devices"][0]["id"] == old["id"]
    before = client.get("/api/projects/" + project["id"]).json()
    assert before["items"][0]["quantity"] == "2"
    preview["configuration"].update(actor="测试维护者", evidence="确认旧清单映射")
    save(client, project, preview["configuration"])
    assert client.get("/api/projects/" + project["id"]).json()["items"][0]["id"] == old["id"]


def test_legacy_topology_preserves_group_sharing_and_geometry(client, catalog, project):
    source = catalog["sources"][0]
    topology = client.post(
        "/api/topologies",
        json=dict(
            name="旧共用方案",
            actor="隔离测试",
            groups=[
                dict(
                    id="g1",
                    name="无纸化",
                    product_line="无纸化",
                    position={"x": 0, "y": 0},
                    width=500,
                    height=500,
                ),
                dict(
                    id="g2",
                    name="会议预约",
                    product_line="会议预约",
                    position={"x": 600, "y": 0},
                    width=500,
                    height=500,
                ),
            ],
            devices=[
                dict(
                    id="server",
                    product_id=source["id"],
                    position={"x": 75, "y": 90},
                    group_id="g1",
                    serves_group_ids=["g2"],
                    role="服务端",
                )
            ],
        ),
    ).json()
    original = client.get("/api/topologies/" + topology["id"]).json()
    preview = client.get(
        BASE + "/projects/" + project["id"] + "/import-preview",
        params={"topology_id": topology["id"]},
    ).json()
    assert preview["unmapped"] == []
    data = preview["configuration"]
    assert len(data["devices"]) == 1 and len(data["requirements"]) == 2
    assert len({r["device_id"] for r in data["requirements"]}) == 1
    root = ET.fromstring(data["drawing_xml"])
    cell = root.find(".//*[@cfg_device_id]")
    geometry = cell.find("mxCell/mxGeometry")
    assert float(geometry.get("x")) == 75 and float(geometry.get("y")) == 90
    assert client.get("/api/topologies/" + topology["id"]).json() == original
