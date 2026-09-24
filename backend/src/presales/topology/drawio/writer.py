import json
from uuid import uuid4
from xml.etree import ElementTree as ET

from .document import Cell, Document

SHAPES = {
    "device": "shape=mxgraph.networks.server;",
    "terminal": "shape=mxgraph.networks.monitor;",
    "switch": "shape=mxgraph.networks.switch;",
    "rack": "shape=mxgraph.networks.rack;",
}
DEVICE_STYLE = (
    "html=0;whiteSpace=wrap;align=center;verticalLabelPosition=bottom;"
    "verticalAlign=top;labelPosition=center;fontSize=12;fontColor=#263445;"
    "fillColor=#f0f4f8;strokeColor=#52677b;strokeWidth=1.5;"
)
GROUP_STYLE = (
    "swimlane;html=0;startSize=36;rounded=0;container=1;collapsible=0;"
    "fillColor=#edf2f7;swimlaneFillColor=#ffffff;strokeColor=#9aaebf;"
    "fontStyle=1;fontSize=14;align=left;spacingLeft=14;"
)
EDGE_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;"
    "strokeColor=#52677b;fontSize=11;labelBackgroundColor=#ffffff;"
)


def metadata(cell: Cell, values: dict):
    element = cell.element
    if element is cell.node:
        element = ET.Element("object", id=cell.local_id, label=cell.node.get("value", ""))
        cell.node.attrib.pop("id", None)
        cell.node.attrib.pop("value", None)
        index = list(cell.root).index(cell.node)
        cell.root.remove(cell.node)
        element.append(cell.node)
        cell.root.insert(index, element)
    for key, value in values.items():
        if key not in {"id", "position", "width", "height", "group_id", "source", "target"}:
            element.set(
                f"ps_{key}",
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, list)
                else str(value)
                if value is not None
                else "",
            )
    return element


def new_cell(document: Document, *, cell_id: str, style: str, parent="1", edge=False, page_id=None):
    page = next((p for p in document.pages if p.get("id") == page_id), document.pages[0])
    root = page.find("mxGraphModel/root")
    element = ET.SubElement(root, "object", id=cell_id, label="")
    node = ET.SubElement(
        element,
        "mxCell",
        style=style,
        parent=parent,
        **({"edge": "1"} if edge else {"vertex": "1"}),
    )
    ET.SubElement(node, "mxGeometry", {"as": "geometry"})
    return Cell(page.get("id"), page.get("name"), root, element, node)


def update_group(cell: Cell, data: dict):
    element = metadata(cell, {**data, "kind": "group"})
    element.set("label", "%ps_name%")
    element.set("placeholders", "1")


def update_device(cell: Cell, data: dict, document: Document):
    metadata(cell, {**data, "kind": "device"})
    parent = document.get(data["group_id"]) if data.get("group_id") else None
    if parent and parent.page != cell.page:
        raise ValueError("放置分组须与设备位于同一页，可用额外服务系统关联其他页")
    if document.parent_group(cell) != data.get("group_id"):
        cell.node.set("parent", parent.local_id if parent else "1")
        cell.node.find("mxGeometry").attrib.update(x="60", y="80")


def update_relation(cell: Cell, data: dict, document: Document):
    source, target = document.get(data["source"]), document.get(data["target"])
    if source.page != target.page or cell.page != source.page:
        raise ValueError("连线两端须位于同一页")
    element = metadata(cell, {**data, "kind": "relation", "relation_kind": data["kind"]})
    cell.node.attrib.update(source=source.local_id, target=target.local_id)
    labels = {
        "required": "必须搭配",
        "optional": "可选搭配",
        "connection": "接口接线",
        "unconfirmed": "待确认",
    }
    element.set("label", labels[data["kind"]])


def add_device(document: Document, *, product: dict, shape="device", cell_id=None):
    cell = new_cell(document, cell_id=cell_id or str(uuid4()), style=SHAPES[shape] + DEVICE_STYLE)
    cell.node.find("mxGeometry").attrib.update(x="120", y="160", width="84", height="84")
    bind_product(cell, product)
    return cell


def bind_product(cell: Cell, product: dict):
    if cell.node.get("vertex") != "1" or cell.get("kind") == "group":
        raise ValueError("请选择普通设备图形绑定产品")
    element = metadata(
        cell,
        dict(
            kind="device",
            product_id=product["id"],
            quantity="1",
            role="",
            note="",
            serves_group_ids=[],
            model=product["model"],
        ),
    )
    element.set("label", "%ps_model%\n数量：%ps_quantity%")
    element.set("placeholders", "1")


def create_drawing(payload: dict):
    document = Document(
        '<mxfile><diagram id="presales" name="主图"><mxGraphModel '
        'grid="1" gridSize="10" page="1" pageWidth="1169" pageHeight="827">'
        '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        "</root></mxGraphModel></diagram></mxfile>"
    )
    for group in payload["groups"]:
        cell = new_cell(document, cell_id=group["id"], style=GROUP_STYLE)
        cell.node.find("mxGeometry").attrib.update(
            **{key: str(value) for key, value in group["position"].items()},
            width=str(group["width"]),
            height=str(group["height"]),
        )
        update_group(cell, group)
    document = Document(document.text())
    for device in payload["devices"]:
        product = payload["products"][device["product_id"]]
        shape = "terminal" if "升降" in product["name"] else "device"
        cell = add_device(document, product=product, cell_id=device["id"], shape=shape)
        update_device(cell, device, document)
        group = next((g for g in payload["groups"] if g["id"] == device["group_id"]), None)
        cell.node.find("mxGeometry").attrib.update(
            **{
                key: str(value - (group["position"][key] if group else 0))
                for key, value in device["position"].items()
            }
        )
    document = Document(document.text())
    for relation in payload["relations"]:
        cell = new_cell(document, cell_id=relation["id"], style=EDGE_STYLE, edge=True)
        cell.node.find("mxGeometry").set("relative", "1")
        update_relation(cell, relation, document)
    return document.text()
