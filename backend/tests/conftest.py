from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from presales.main import create_app
from presales.storage import Base


@pytest.fixture
def workbook():
    cells = {
        "A1": "产品型号",
        "B1": "产品名称",
        "C1": "性能描述(完整参数）",
        "D1": "备注",
        "E1": "出厂指导价",
        "F1": "甲方指导价",
        "G1": "单位",
        "A2": "SERVER-X",
        "B2": "服务器",
        "C2": "64GB",
        "D2": "需要核对部署容量",
        "E2": "按项目申请",
        "G2": "台",
        "A3": "SERVER-X",
        "B3": "服务器",
        "C3": "128GB",
        "G3": "台",
    }
    sheet_cells = "".join(
        f'<row r="{index}">'
        + "".join(
            f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            for address, value in cells.items()
            if address.endswith(str(index))
        )
        + "</row>"
        for index in range(1, 4)
    )
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f"<workbook {ns} "
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="产品表" sheetId="1" r:id="rId1" state="hidden"/>'
            "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            "<Relationships>"
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f"<worksheet {ns}>"
            '<dimension ref="A1:XFD1000000"/><sheetData>'
            + sheet_cells
            + '</sheetData><mergeCells><mergeCell ref="D2:D3"/>'
            '<mergeCell ref="E2:F3"/></mergeCells></worksheet>',
        )
    return stream.getvalue()


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with TestClient(create_app(session_factory=factory)) as test_client:
        yield test_client
    engine.dispose()
