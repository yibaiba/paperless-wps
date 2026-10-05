from presales.storage import identifier
from presales.topology.drawio.document import Document
from presales.topology.drawio.writer import DEVICE_STYLE, SHAPES, new_cell

EMPTY_XML = (
    '<mxfile><diagram id="presales" name="项目配置"><mxGraphModel>'
    '<root><mxCell id="0"/><mxCell id="1" parent="0"/></root>'
    "</mxGraphModel></diagram></mxfile>"
)


def project_drawing(xml, *, devices, add_ids=()):
    additions = ((index, index, identity) for index, identity in enumerate(add_ids))
    return project_additions(xml, devices=devices, additions=additions)


def project_device_sequence(xml, *, devices, add_ids=()):
    # Each device_put previously added one node with position index 0. Keep that layout.
    additions = ((0, index, identity) for index, identity in enumerate(add_ids))
    return project_additions(xml, devices=devices, additions=additions)


def project_additions(xml, *, devices, additions):
    document = Document(xml or EMPTY_XML)
    by_id = {d["id"]: d for d in devices}
    for cell in document.cells.values():
        device_id = cell.element.get("cfg_device_id")
        if device_id and device_id not in by_id:
            raise ValueError("图形引用的设备不存在，请通过删除设备操作同步移除图形引用")
        if device_id:
            label(cell.element, by_id[device_id])
    for column_index, row_index, device_id in additions:
        if device_id not in by_id:
            raise ValueError("新增图形引用的设备不存在")
        cell = new_cell(document, cell_id=identifier(), style=SHAPES["device"] + DEVICE_STYLE)
        cell.node.find("mxGeometry").attrib.update(
            x=str(120 + column_index % 4 * 180),
            y=str(160 + (len(document.cells) + row_index) // 4 * 180),
            width="84",
            height="84",
        )
        cell.element.set("cfg_device_id", device_id)
        label(cell.element, by_id[device_id])
    return document.text()


def label(element, device):
    element.set("label", f"{device['name']}\n数量：{device['quantity']}")
    element.attrib.pop("placeholders", None)


def remove_device_references(xml, device_id):
    from presales.topology.drawio.service import remove

    doc = Document(xml or EMPTY_XML)
    ids = [c.id for c in doc.cells.values() if c.element.get("cfg_device_id") == device_id]
    for cell_id in ids:
        if cell_id in doc.cells:
            remove(doc, cell_id)
            doc = Document(doc.text())
    return doc.text()
