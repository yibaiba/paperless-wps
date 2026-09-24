from .document import Document
from .placement import add_products
from .reader import inspect
from .writer import (
    EDGE_STYLE,
    GROUP_STYLE,
    add_device,
    bind_product,
    metadata,
    new_cell,
    update_device,
    update_group,
    update_relation,
)


def remove(document: Document, cell_id: str):
    cell = document.get(cell_id)
    descendants = {cell.local_id}
    if cell.get("kind") == "group":
        devices = {d["id"]: d for d in inspect(document)["devices"]}
        for child in document.cells.values():
            if child.page == cell.page and child.node.get("parent") == cell.local_id:
                child.node.set("parent", cell.node.get("parent", "1"))
                geometry = child.node.find("mxGeometry")
                if geometry is not None and geometry.get("relative") != "1":
                    geometry.attrib.update(
                        **{key: str(child.position[key] + cell.position[key]) for key in ("x", "y")}
                    )
            if child.get("kind") == "device":
                device = devices[child.id]
                metadata(
                    child,
                    {"serves_group_ids": [g for g in device["serves_group_ids"] if g != cell.id]},
                )
    else:
        # Native compound symbols can contain child graphics and attached connectors.
        changed = True
        while changed:
            before = len(descendants)
            descendants.update(
                c.local_id
                for c in document.cells.values()
                if c.page == cell.page and c.node.get("parent") in descendants
            )
            changed = before != len(descendants)
    for item in document.cells.values():
        if item.page != cell.page:
            continue
        if (
            item.local_id in descendants
            or item.node.get("source") in descendants
            or item.node.get("target") in descendants
        ):
            item.root.remove(item.element)


def modify(document: Document, operation, *, product=None, products=None):
    if operation.action == "add_product":
        if operation.bind_id:
            bind_product(document.get(operation.bind_id), product)
        else:
            add_device(document, product=product, shape=operation.shape)
    elif operation.action == "add_products":
        add_products(document, products=products, shape=operation.shape)
    elif operation.action == "device":
        data = operation.device.model_dump(mode="json")
        update_device(document.get(data["id"]), data, document)
    elif operation.action == "group":
        data = operation.group.model_dump(mode="json")
        cell = document.cells.get(data["id"])
        if cell is None:
            cell = new_cell(document, cell_id=data["id"], style=GROUP_STYLE)
            cell.node.find("mxGeometry").attrib.update(x="40", y="40", width="600", height="360")
        update_group(cell, data)
    elif operation.action == "relation":
        edit_relation(document, operation.relation.model_dump(mode="json"))
    elif operation.action == "remove":
        remove(document, operation.id)
    return Document(document.text())


def edit_relation(document: Document, data: dict):
    cell = document.cells.get(data["id"])
    if cell is None:
        source = document.get(data["source"])
        cell = new_cell(
            document, cell_id=data["id"], style=EDGE_STYLE, edge=True, page_id=source.page
        )
        cell.node.find("mxGeometry").set("relative", "1")
    update_relation(cell, data, document)


def business_data(xml: str):
    data = inspect(Document(xml))
    return {key: data[key] for key in ("groups", "devices", "relations")}
