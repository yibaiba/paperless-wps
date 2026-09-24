import json

from .document import Cell, Document, identifier


def device(cell: Cell, document: Document):
    try:
        serves = json.loads(cell.get("serves_group_ids", "[]"))
    except json.JSONDecodeError as error:
        raise ValueError("设备的额外服务系统数据无效") from error
    return dict(
        id=cell.id,
        product_id=cell.get("product_id"),
        position=cell.position,
        quantity=cell.get("quantity", "1"),
        group_id=document.parent_group(cell),
        role=cell.get("role"),
        serves_group_ids=serves,
        note=cell.get("note"),
    )


def group(cell: Cell):
    geometry = cell.node.find("mxGeometry")
    if geometry is None:
        raise ValueError("系统分组缺少尺寸")
    return dict(
        id=cell.id,
        name=cell.get("name"),
        product_line=cell.get("product_line"),
        position=cell.position,
        width=geometry.get("width"),
        height=geometry.get("height"),
    )


def relation(cell: Cell):
    return dict(
        id=cell.id,
        source=identifier(cell.page, cell.node.get("source", "")),
        target=identifier(cell.page, cell.node.get("target", "")),
        kind=cell.get("relation_kind", "unconfirmed"),
        mode=cell.get("mode", "per_unit"),
        factor=cell.get("factor", "1"),
        evidence=cell.get("evidence"),
        source_port=cell.get("source_port"),
        target_port=cell.get("target_port"),
        cable=cell.get("cable"),
        length_m=cell.get("length_m") or None,
    )


def inspect(document: Document):
    groups, devices, relations, shapes, edges = [], [], [], [], []
    for cell in document.cells.values():
        kind = cell.get("kind")
        if kind == "group":
            groups.append(group(cell))
        elif kind == "device":
            if cell.node.get("vertex") != "1":
                raise ValueError("产品绑定必须对应设备图形")
            devices.append(device(cell, document))
        elif cell.node.get("vertex") == "1":
            shapes.append(
                dict(
                    id=cell.id,
                    label=cell.element.get("label") or cell.node.get("value") or "未命名图形",
                    page=cell.page_name,
                )
            )
    device_ids = {item["id"] for item in devices}
    for cell in document.cells.values():
        if cell.node.get("edge") != "1":
            continue
        data = relation(cell)
        if {data["source"], data["target"]} <= device_ids:
            relations.append(data)
        elif cell.get("kind") == "relation":
            raise ValueError("业务关系的两端须连接已绑定产品的图形，请重新连接或删除该关系")
        else:
            edges.append(dict(id=cell.id, page=cell.page_name))
    return dict(
        groups=groups,
        devices=devices,
        relations=relations,
        unbound_shapes=shapes,
        drawing_only_edges=edges,
    )
