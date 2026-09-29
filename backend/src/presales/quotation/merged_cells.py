"""Read merge provenance while retaining the streaming cell importer."""

import posixpath
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from openpyxl.worksheet.cell_range import CellRange

from presales.catalog.xlsx_reader import NS, REL_ID


def workbook_merges(content):
    try:
        with ZipFile(BytesIO(content)) as archive:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {r.attrib["Id"]: r.attrib["Target"] for r in relations}
            sheets = workbook.find("s:sheets", NS)
            if sheets is None:
                raise ValueError("工作簿缺少工作表目录")
            return {
                sheet.attrib["name"]: sheet_merges(archive, targets[sheet.attrib[REL_ID]])
                for sheet in sheets
            }
    except (BadZipFile, KeyError, ElementTree.ParseError, DefusedXmlException) as error:
        raise ValueError("无法读取工作簿合并区域，请检查 XLSX 文件") from error


def sheet_merges(archive, target):
    path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
    if not path.startswith("xl/") or ".." in path.split("/"):
        raise ValueError("工作簿的工作表引用无效")
    merges = []
    with archive.open(path) as source:
        for _, element in ElementTree.iterparse(source, events=("end",)):
            if element.tag == "{" + NS["s"] + "}mergeCell":
                region = CellRange(element.attrib["ref"])
                merges.append(
                    dict(
                        range=region.coord,
                        start_row=region.min_row,
                        end_row=region.max_row,
                        start_column=region.min_col,
                        end_column=region.max_col,
                    )
                )
            element.clear()
    return merges
