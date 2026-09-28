from fastapi import APIRouter, UploadFile

from presales.configuration.http import execute

from .importing import workbook_cells

router = APIRouter(prefix="/api/quotation")


@router.post("/import-cells")
def import_cells(file: UploadFile):
    def read():
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise ValueError("请选择 .xlsx 工作簿；旧版 .xls 请先另存为 .xlsx")
        return workbook_cells(file.file.read())

    return execute(read)
