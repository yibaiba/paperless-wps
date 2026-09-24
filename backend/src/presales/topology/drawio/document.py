"""Lossless draw.io XML storage with page-scoped business identifiers."""

import base64
import binascii
import json
import zlib
from dataclasses import dataclass
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

PRIMARY_PAGE = "presales"


def identifier(page: str, cell: str) -> str:
    if page == PRIMARY_PAGE:
        return cell
    raw = json.dumps([page, cell], ensure_ascii=False).encode()
    return "drawio-" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def parse_xml(xml: str):
    try:
        return SafeET.fromstring(xml, forbid_dtd=True)
    except (ET.ParseError, DefusedXmlException) as error:
        raise ValueError("图纸 XML 无效或含有不允许的实体定义") from error


@dataclass(frozen=True)
class Cell:
    page: str
    page_name: str
    root: ET.Element
    element: ET.Element
    node: ET.Element

    @property
    def local_id(self):
        return self.element.get("id", "")

    @property
    def id(self):
        return identifier(self.page, self.local_id)

    def get(self, name: str, default=""):
        return self.element.get(f"ps_{name}", default)

    @property
    def position(self):
        geometry = self.node.find("mxGeometry")
        return {
            key: float(geometry.get(key, "0")) if geometry is not None else 0 for key in ("x", "y")
        }


class Document:
    def __init__(self, xml: str):
        self.xml = parse_xml(xml)
        if self.xml.tag == "mxGraphModel":
            model = self.xml
            self.xml = ET.Element("mxfile")
            ET.SubElement(self.xml, "diagram", id=PRIMARY_PAGE, name="主图").append(model)
        if self.xml.tag != "mxfile" or not self.xml.findall("diagram"):
            raise ValueError("图纸须为 draw.io 的 mxfile 或 mxGraphModel")
        self.cells = {}
        self.pages = []
        self._read_pages()

    def _read_pages(self):
        for page in self.xml.findall("diagram"):
            page_id = page.get("id")
            if not page_id or any(p.get("id") == page_id for p in self.pages):
                raise ValueError("图纸页面标识缺失或重复")
            model = page.find("mxGraphModel")
            if model is None:
                model = self._decompress(page.text or "")
                page.text = None
                page.append(model)
            root = model.find("root")
            if root is None:
                raise ValueError("图纸缺少 root 节点")
            self.pages.append(page)
            for element in root:
                node = element if element.tag == "mxCell" else element.find("mxCell")
                if node is None:
                    continue
                cell = Cell(page_id, page.get("name", page_id), root, element, node)
                if not cell.local_id or cell.id in self.cells:
                    raise ValueError("图形标识缺失或重复")
                self.cells[cell.id] = cell

    @staticmethod
    def _decompress(text: str):
        try:
            xml = zlib.decompress(base64.b64decode(text, validate=True), -15).decode("utf-8")
            model = parse_xml(unquote(xml))
        except (binascii.Error, zlib.error, UnicodeError) as error:
            raise ValueError("无法解压 draw.io 图纸页面") from error
        if model.tag != "mxGraphModel":
            raise ValueError("页面不是 mxGraphModel")
        return model

    def get(self, cell_id: str) -> Cell:
        cell = self.cells.get(cell_id)
        if cell is None:
            raise ValueError("图形已不存在，请重新打开业务面板")
        return cell

    def parent_group(self, cell: Cell):
        visited = {cell.id}
        parent = cell.node.get("parent")
        while parent:
            key = identifier(cell.page, parent)
            if key in visited:
                raise ValueError("图形分组存在循环引用")
            visited.add(key)
            ancestor = self.cells.get(key)
            if ancestor is None:
                raise ValueError("图形引用的父节点不存在")
            if ancestor.get("kind") == "group":
                return ancestor.id
            parent = ancestor.node.get("parent")
        return None

    def text(self):
        return ET.tostring(self.xml, encoding="unicode")
