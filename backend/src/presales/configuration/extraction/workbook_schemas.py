from openpyxl.worksheet.cell_range import CellRange
from pydantic import Field, model_validator

from ..common import Authored, Input, Text


class WorkbookRange(Input):
    sheet: Text
    range: Text

    @model_validator(mode="after")
    def valid_range(self):
        region = CellRange(self.range)
        if region.title or region.max_col > 16384 or region.max_row > 1048576:
            raise ValueError("请选择有效的 XLSX 单元格范围，工作表单独指定")
        return self


class WorkbookMaterial(Authored):
    name: Text
    digest: Text
    ranges: list[WorkbookRange] = Field(min_length=1)
    operation_id: Text
    material_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def revision_pair(self):
        if bool(self.material_id) != bool(self.expected_revision):
            raise ValueError("更新资料需要同时指定资料 ID 和预期修订")
        return self
