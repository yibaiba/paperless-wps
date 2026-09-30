from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from presales.configuration.common import Input, Text

TemplateField = Literal[
    "model", "name", "description", "quantity", "unit", "brand", "price", "note", "section"
]
ManagedField = Literal["model", "name", "description", "unit", "brand", "price"]
MAX_SPREADSHEET_COLUMN = 16384
FEEDBACK_PREVIOUS_CONTEXT_LIMIT = 3
FEEDBACK_NEXT_CONTEXT_LIMIT = 1


class PairingExchange(Input):
    code: Text


class TemplateProfileWrite(Input):
    profile_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    name: Text
    sheet_selector: Text
    header_row: int = Field(ge=1)
    field_columns: dict[TemplateField, int]
    managed_fields: list[ManagedField] = Field(default_factory=list)
    header_values: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_mapping(self):
        if "quantity" not in self.field_columns:
            raise ValueError("模板必须映射数量列")
        if not ({"model", "name"} & self.field_columns.keys()):
            raise ValueError("模板必须映射型号或名称列")
        if len(set(self.field_columns.values())) != len(self.field_columns):
            raise ValueError("一个工作表列不能映射到多个业务字段")
        if any(not 1 <= index <= MAX_SPREADSHEET_COLUMN for index in self.field_columns.values()):
            raise ValueError("列号超出 WPS 表格范围")
        if set(self.managed_fields) - self.field_columns.keys():
            raise ValueError("插件管理字段必须已经映射")
        if not ({"model", "name"} & set(self.managed_fields)):
            raise ValueError("产品型号或名称至少有一项须由插件填写")
        if bool(self.profile_id) != bool(self.expected_revision):
            raise ValueError("修改模板时需要同时指定模板 ID 和期望修订")
        return self


class SuggestionContext(Input):
    sheet: str = ""
    section: str = ""
    system: str = ""
    role: str = ""
    selected_variant_id: str | None = None
    previous_variant_ids: list[str] = Field(default_factory=list, max_length=8)
    next_variant_ids: list[str] = Field(default_factory=list, max_length=3)


class SuggestionRequest(Input):
    query: str = ""
    workbook_instance_id: str | None = None
    template_profile_id: str | None = None
    template_profile_revision: int | None = Field(default=None, ge=1)
    draft_id: str | None = None
    requirement_id: str | None = None
    current_row: dict[TemplateField, str] = Field(default_factory=dict)
    context: SuggestionContext = Field(default_factory=SuggestionContext)
    limit: int = Field(default=12, ge=1, le=30)


class SuggestionFeedbackWrite(Input):
    operation_id: Text
    workbook_instance_id: Text
    template_profile_id: Text
    template_profile_revision: int = Field(ge=1)
    sheet: str = ""
    section: str = ""
    previous_variant_id: str | None = None
    context_previous_variant_ids: list[str] = Field(
        default_factory=list, max_length=FEEDBACK_PREVIOUS_CONTEXT_LIMIT
    )
    context_next_variant_ids: list[str] = Field(
        default_factory=list, max_length=FEEDBACK_NEXT_CONTEXT_LIMIT
    )
    suggested_variant_id: str | None = None
    chosen_variant_id: Text
    chosen_source_id: Text
    query_kind: Literal["contextual", "typed"]


class BindingCreate(Input):
    workbook_instance_id: Text
    name: Text
    project_id: str | None = None
    project_revision: int | None = Field(default=None, ge=1)
    template_profile_id: Text
    template_profile_revision: int = Field(ge=1)
    operation_id: Text

    @model_validator(mode="after")
    def project_base(self):
        if bool(self.project_id) != bool(self.project_revision):
            raise ValueError("绑定已有项目需要同时指定项目 ID 和版本")
        return self


class WorkbookLine(Input):
    line_id: Text
    sheet: Text
    row: int = Field(ge=1)
    model: str = ""
    name: str = ""
    description: str = ""
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    unit: str = ""
    brand: str = ""
    price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    note: str = ""
    section: str = ""
    kind: Literal["hardware", "software", "license", "accessory"] = "hardware"
    variant_id: Text
    source_id: Text
    device_id: str | None = None


class SyncPreview(Input):
    binding_id: Text
    expected_draft_revision: int = Field(ge=1)
    expected_project_revision: int = Field(ge=0)
    template_profile_revision: int = Field(ge=1)
    known_device_ids: list[str] = Field(default_factory=list)
    lines: list[WorkbookLine]

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("工作簿行标识不能重复")
        if len(set(self.known_device_ids)) != len(self.known_device_ids):
            raise ValueError("已绑定设备标识不能重复")
        return self


class SyncCommit(SyncPreview):
    preview_fingerprint: Text
    operation_id: Text
