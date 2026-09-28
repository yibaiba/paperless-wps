from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field, model_validator

from ..common import Authored, Input, Text

UNITS = {"GB", "MB", "TB", "mm", "cm", "m", "W", "台", "个", "路", "席", "核"}


class Attribute(Input):
    key: Text
    kind: Literal["text", "enum", "number", "quantity"] = "text"
    value: str | list[str] | Decimal | None = None
    unit: str = ""

    @model_validator(mode="after")
    def valid_value(self):
        if self.kind == "quantity" and self.unit not in UNITS:
            raise ValueError("请选择支持的单位：" + "、".join(sorted(UNITS)))
        if self.kind != "quantity" and self.unit:
            raise ValueError("只有带单位数值可以填写单位")
        if self.value is None:
            return self
        if self.kind in {"number", "quantity"}:
            try:
                value = Decimal(str(self.value))
            except InvalidOperation as error:
                raise ValueError("数值属性必须是数字") from error
            if not value.is_finite():
                raise ValueError("数值必须有限")
        if self.kind == "text" and not isinstance(self.value, str):
            raise ValueError("文字属性必须是文本")
        if self.kind == "enum" and not isinstance(self.value, list):
            raise ValueError("枚举属性须为选项列表")
        return self


class ProductInput(Authored):
    name: Text
    model: Text
    brand: str = ""
    category: str = ""


class VariantInput(Authored):
    capability_ids: list[str] = Field(default_factory=list)
    product_id: Text
    name: Text
    status: Literal["draft", "confirmed"] = "draft"
    attributes: list[Attribute] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({a.key for a in self.attributes}) != len(self.attributes):
            raise ValueError("属性名称不能重复")
        return self


class LinkItem(Input):
    source_id: Text
    expected_revision: int = Field(ge=0)


class SourceBatch(Authored):
    items: list[LinkItem] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({i.source_id for i in self.items}) != len(self.items):
            raise ValueError("不能重复选择同一来源")
        return self


class LinkInput(SourceBatch):
    variant_id: Text


class SourceBlockInput(SourceBatch):
    reason: Text
