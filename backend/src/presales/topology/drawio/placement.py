"""Place a selection below the existing first-page drawing in a readable grid."""

from .document import Document, identifier
from .writer import add_device

GRID_COLUMNS = 4
COLUMN_SPACING = 180
ROW_SPACING = 180
DRAWING_GAP = 100
START_X = 120
START_Y = 160


def drawing_bottom(document: Document):
    bottoms = []
    for cell in document.cells.values():
        if cell.page != document.pages[0].get("id") or cell.node.get("vertex") != "1":
            continue
        geometry = cell.node.find("mxGeometry")
        if geometry is None:
            continue
        bottom = cell.position["y"] + float(geometry.get("height", "0"))
        parent = cell.node.get("parent")
        visited = {cell.id}
        while parent:
            ancestor = document.get(identifier(cell.page, parent))
            if ancestor.id in visited:
                raise ValueError("图形分组存在循环引用")
            visited.add(ancestor.id)
            bottom += ancestor.position["y"]
            parent = ancestor.node.get("parent")
        bottoms.append(bottom)
    return max(bottoms, default=START_Y - DRAWING_GAP)


def add_products(document: Document, *, products: list[dict], shape: str):
    start_y = max(START_Y, drawing_bottom(document) + DRAWING_GAP)
    for index, product in enumerate(products):
        cell = add_device(document, product=product, shape=shape)
        cell.node.find("mxGeometry").attrib.update(
            x=str(START_X + index % GRID_COLUMNS * COLUMN_SPACING),
            y=str(start_y + index // GRID_COLUMNS * ROW_SPACING),
        )
