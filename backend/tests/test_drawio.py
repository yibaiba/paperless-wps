import base64
import zlib
from copy import deepcopy
from urllib.parse import quote
from xml.etree import ElementTree as ET

import pytest

from presales.topology.drawio.document import Document
from presales.topology.drawio.writer import create_drawing


@pytest.fixture
def drawing_setup(client, workbook):
    imported = client.post("/api/imports", files={"file": ("drawing.xlsx", workbook)}).json()
    products = client.get("/api/products", params={"import_id": imported["id"]}).json()
    xml = create_drawing(dict(groups=[], devices=[], relations=[], products={}))
    return xml, products


def edit(client, xml, operation=None):
    response = client.post("/api/topologies/drawing", json=dict(xml=xml, operation=operation))
    response.raise_for_status()
    return response.json()


def product(client, xml, record, **options):
    return edit(client, xml, dict(action="add_product", product_id=record["id"], **options))


def save(client, drawing):
    response = client.post(
        "/api/topologies",
        json=dict(name="绘图验证", actor="测试", drawing_xml=drawing["drawing_xml"]),
    )
    response.raise_for_status()
    return response.json()


def test_product_quantity_authoritative_roundtrip_and_revision(client, drawing_setup):
    xml, products = drawing_setup
    drawing = product(client, xml, products[0], shape="terminal")
    device = {**drawing["devices"][0], "quantity": "2.50", "role": "共用服务"}
    drawing = edit(client, drawing["drawing_xml"], dict(action="device", device=device))
    saved = save(client, drawing)
    assert saved["devices"][0]["quantity"] == "2.50"
    assert saved["bom"][0]["quantity"] == "2.50"
    document = Document(saved["drawing_xml"])
    document.get(device["id"]).element.set("ps_quantity", "3.5")
    updated = client.put(
        f"/api/topologies/{saved['id']}",
        json=dict(
            name="绘图验证",
            actor="测试",
            drawing_xml=document.text(),
            expected_revision=1,
            devices=[{**device, "quantity": "999"}],
        ),
    )
    assert updated.status_code == 200
    assert updated.json()["bom"][0]["quantity"] == "3.5"
    history = client.get(f"/api/topologies/{saved['id']}/history").json()
    assert history[1]["drawing_xml"] == saved["drawing_xml"]
    assert history[1]["bom"][0]["quantity"] == "2.50"


def test_native_shape_binding_preserves_style_waypoints_and_drawing_only_shapes(
    client, drawing_setup
):
    xml, products = drawing_setup
    doc = Document(xml)
    root = doc.pages[0].find("mxGraphModel/root")
    native = ET.SubElement(
        root,
        "mxCell",
        id="monitor",
        value="监视器",
        vertex="1",
        parent="1",
        style="shape=mxgraph.networks.monitor;fillColor=#00ff00;rotation=30;",
    )
    ET.SubElement(
        native, "mxGeometry", width="90", height="70", x="20", y="30", **{"as": "geometry"}
    )
    ET.SubElement(root, "mxCell", id="title", value="说明文字", vertex="1", parent="1")
    drawing = edit(client, doc.text())
    assert len(drawing["unbound_shapes"]) == 2
    bound = product(client, doc.text(), products[0], bind_id="monitor")
    assert len(bound["devices"]) == 1
    assert len(bound["unbound_shapes"]) == 1
    assert Document(bound["drawing_xml"]).get("monitor").node.get("style") == native.get("style")
    saved = save(client, bound)
    assert "说明文字" in saved["drawing_xml"]


def test_native_edge_becomes_unconfirmed_then_rule_and_preserves_waypoints(client, drawing_setup):
    xml, products = drawing_setup
    drawing = product(client, xml, products[0])
    drawing = product(client, drawing["drawing_xml"], products[1])
    source, target = [d["id"] for d in drawing["devices"]]
    doc = Document(drawing["drawing_xml"])
    root = doc.pages[0].find("mxGraphModel/root")
    edge = ET.SubElement(
        root,
        "mxCell",
        id="wire",
        edge="1",
        parent="1",
        source=source,
        target=target,
        style="edgeStyle=orthogonalEdgeStyle;strokeColor=#ff0000;",
    )
    geometry = ET.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})
    ET.SubElement(geometry, "mxPoint", x="260", y="300", **{"as": "targetPoint"})
    drawing = edit(client, doc.text())
    assert drawing["relations"][0]["kind"] == "unconfirmed"
    relation = {
        **drawing["relations"][0],
        "kind": "required",
        "mode": "per_group",
        "factor": "1",
        "evidence": "已确认测试依据",
    }
    drawing = edit(client, drawing["drawing_xml"], dict(action="relation", relation=relation))
    assert "targetPoint" in drawing["drawing_xml"]
    assert "#ff0000" in drawing["drawing_xml"]
    saved = save(client, drawing)
    rule = client.post(
        f"/api/topologies/{saved['id']}/relations/wire/rule",
        json={"expected_revision": 1, "actor": "测试"},
    )
    assert rule.status_code == 200
    assert rule.json()["status"] == "draft"
    doc = Document(drawing["drawing_xml"])
    doc.get("wire").node.attrib.pop("target")
    assert client.post("/api/topologies/drawing", json={"xml": doc.text()}).status_code == 422


def test_compressed_multiple_pages_and_copied_nodes_have_distinct_ids(client, drawing_setup):
    xml, products = drawing_setup
    drawing = product(client, xml, products[0])
    document = Document(drawing["drawing_xml"])
    page = deepcopy(document.pages[0])
    page.set("id", "second-page")
    page.set("name", "第二页")
    model = page.find("mxGraphModel")
    encoded = quote(ET.tostring(model, encoding="unicode"), safe="").encode()
    compressor = zlib.compressobj(wbits=-15)
    page.remove(model)
    page.text = base64.b64encode(compressor.compress(encoded) + compressor.flush()).decode()
    document.xml.append(page)
    drawing = edit(client, document.text())
    assert len({d["id"] for d in drawing["devices"]}) == 2
    assert save(client, drawing)["bom"][0]["quantity"] == "2"
    second = drawing["devices"][1]
    changed = edit(
        client, drawing["drawing_xml"], dict(action="device", device={**second, "quantity": "4"})
    )
    assert [d["quantity"] for d in changed["devices"]] == ["1", "4"]


def test_system_membership_and_shared_counts_removal(client, drawing_setup):
    xml, products = drawing_setup
    group = dict(
        id="room",
        name="会议室",
        product_line="无纸化",
        position={"x": 40, "y": 40},
        width=600,
        height=360,
    )
    drawing = edit(client, xml, dict(action="group", group=group))
    drawing = product(client, drawing["drawing_xml"], products[0])
    device = {**drawing["devices"][0], "group_id": "room", "serves_group_ids": ["room"]}
    drawing = edit(client, drawing["drawing_xml"], dict(action="device", device=device))
    assert drawing["devices"][0]["group_id"] == "room"
    assert save(client, drawing)["bom"][0]["quantity"] == "1"
    drawing = edit(client, drawing["drawing_xml"], dict(action="remove", id="room"))
    assert drawing["groups"] == []
    assert drawing["devices"][0]["position"] == {"x": 100, "y": 120}
    assert drawing["devices"][0]["group_id"] is None
    assert drawing["devices"][0]["serves_group_ids"] == []
    drawing = edit(client, drawing["drawing_xml"], dict(action="remove", id=device["id"]))
    assert drawing["devices"] == []


@pytest.mark.parametrize(
    "xml",
    [
        "<invalid>",
        "<root/>",
        '<!DOCTYPE x [<!ENTITY boom "entity">]><mxGraphModel>&boom;</mxGraphModel>',
        '<mxfile><diagram id="bad">not deflate</diagram></mxfile>',
        "<mxfile><diagram><mxGraphModel><root/></mxGraphModel></diagram></mxfile>",
    ],
)
def test_invalid_xml_fails_explicitly(client, xml):
    response = client.post("/api/topologies/drawing", json={"xml": xml})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("ps_quantity", "0"),
        ("ps_quantity", "NaN"),
        ("ps_product_id", "missing"),
        ("ps_serves_group_ids", "["),
    ],
)
def test_invalid_business_metadata_not_silently_ignored(client, drawing_setup, attribute, value):
    xml, products = drawing_setup
    drawing = product(client, xml, products[0])
    doc = Document(drawing["drawing_xml"])
    doc.get(drawing["devices"][0]["id"]).element.set(attribute, value)
    assert client.post("/api/topologies/drawing", json={"xml": doc.text()}).status_code == 422


def test_batch_add_preserves_order_existing_drawing_and_separate_positions(client, drawing_setup):
    xml, products = drawing_setup
    before = product(client, xml, products[0])
    existing = before["devices"][0]
    ids = [p["id"] for p in reversed(products)]
    drawing = edit(
        client,
        before["drawing_xml"],
        dict(action="add_products", product_ids=ids, shape="terminal"),
    )
    assert drawing["devices"][0] == existing
    added = drawing["devices"][1:]
    assert [d["product_id"] for d in added] == ids
    assert all(d["quantity"] == "1" for d in added)
    positions = {(d["position"]["x"], d["position"]["y"]) for d in drawing["devices"]}
    assert len(positions) == len(drawing["devices"])
    assert min(d["position"]["y"] for d in added) > existing["position"]["y"] + 84
    assert all(
        "monitor" in Document(drawing["drawing_xml"]).get(d["id"]).node.get("style") for d in added
    )
    saved = save(client, drawing)
    assert len(saved["devices"]) == len(products) + 1
    again = edit(client, drawing["drawing_xml"], dict(action="add_products", product_ids=ids))
    assert min(d["position"]["y"] for d in again["devices"][len(drawing["devices"]) :]) > max(
        d["position"]["y"] for d in added
    )


@pytest.mark.parametrize("selection", ["empty", "duplicate", "missing"])
def test_invalid_batch_add_does_not_change_saved_topology(client, drawing_setup, selection):
    xml, products = drawing_setup
    saved = save(client, product(client, xml, products[0]))
    ids = {
        "empty": [],
        "duplicate": [products[0]["id"]] * 2,
        "missing": [products[0]["id"], "missing-product"],
    }[selection]
    response = client.post(
        "/api/topologies/drawing",
        json={
            "xml": saved["drawing_xml"],
            "operation": {"action": "add_products", "product_ids": ids},
        },
    )
    assert response.status_code == 422
    unchanged = client.get(f"/api/topologies/{saved['id']}").json()
    assert unchanged["drawing_xml"] == saved["drawing_xml"]
    assert unchanged["revision"] == saved["revision"]


def test_batch_grid_wraps_below_nested_existing_content():
    from presales.topology.drawio.placement import add_products

    doc = Document(create_drawing(dict(groups=[], devices=[], relations=[], products={})))
    root = doc.pages[0].find("mxGraphModel/root")
    parent = ET.SubElement(root, "mxCell", id="container", vertex="1", parent="1")
    ET.SubElement(parent, "mxGeometry", x="20", y="400", width="300", height="100")
    child = ET.SubElement(root, "mxCell", id="child", vertex="1", parent="container")
    ET.SubElement(child, "mxGeometry", x="20", y="200", width="84", height="84")
    doc = Document(doc.text())
    add_products(
        doc, products=[dict(id=str(i), model=f"Product {i}") for i in range(5)], shape="device"
    )
    devices = [c for c in Document(doc.text()).cells.values() if c.get("kind") == "device"]
    assert len(devices) == 5
    assert devices[0].position["y"] > 400 + 200 + 84
    assert len({d.position["x"] for d in devices[:4]}) == 4
    assert devices[4].position["x"] == devices[0].position["x"]
    assert devices[4].position["y"] > devices[0].position["y"] + 84
