import posixpath
import re
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from .models import SourceSheet

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
CELL = re.compile(r"([A-Z]+)(\d+)$")


def split_cell(address: str) -> tuple[str, int]:
    match = CELL.fullmatch(address)
    if not match:
        raise ValueError(f"无效单元格地址：{address}")
    return match[1], int(match[2])


def read_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in item.findall(".//s:t", NS)) for item in root]


def cell_value(cell, strings: list[str]) -> str:
    if cell.find("s:f", NS) is not None:
        return ""  # Formula caches are not authoritative product data.
    if cell.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//s:t", NS)).strip()
    raw = cell.findtext("s:v", default="", namespaces=NS)
    return (strings[int(raw)] if cell.get("t") == "s" and raw else raw).strip()


def read_sheet(archive: ZipFile, sheet, context: dict) -> SourceSheet:
    target = context["targets"][sheet.attrib[REL_ID]]
    path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
    if not path.startswith("xl/") or ".." in path.split("/"):
        raise ValueError("工作簿的工作表引用无效")
    root = ElementTree.fromstring(archive.read(path))
    cells = {
        cell.attrib["r"]: cell_value(cell, context["strings"])
        for cell in root.findall("s:sheetData/s:row/s:c", NS)
    }
    return SourceSheet(
        name=sheet.attrib["name"],
        hidden=sheet.get("state", "visible") != "visible",
        cells={key: value for key, value in cells.items() if value},
        merges=tuple(m.attrib["ref"] for m in root.findall("s:mergeCells/s:mergeCell", NS)),
    )


def read_workbook(content: bytes) -> tuple[SourceSheet, ...]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            context = {
                "targets": {r.attrib["Id"]: r.attrib["Target"] for r in relations},
                "strings": read_strings(archive),
            }
            sheets = workbook.find("s:sheets", NS)
            if sheets is None:
                raise ValueError("工作簿缺少工作表目录")
            return tuple(read_sheet(archive, s, context) for s in sheets)
    except (BadZipFile, KeyError, IndexError, ElementTree.ParseError, DefusedXmlException) as error:
        raise ValueError("无法读取工作簿，请上传有效的 .xlsx 文件") from error
