from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ..catalog.schemas import UNITS
from ..common import Authored, Input, Text


class Condition(Input):
    field: Text
    operator: Literal["eq", "any", "all", "range"]
    value: str | list[str] | None = None
    minimum: Decimal | None = Field(default=None, allow_inf_nan=False)
    maximum: Decimal | None = Field(default=None, allow_inf_nan=False)
    unit: str = ""

    @model_validator(mode="after")
    def complete(self):
        if self.unit and self.unit not in UNITS:
            raise ValueError("条件单位不受支持")
        if self.operator == "range":
            if self.minimum is None and self.maximum is None:
                raise ValueError("范围条件至少填写一个边界")
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise ValueError("下限不能大于上限")
        elif self.value is None:
            raise ValueError("请填写条件值")
        if self.operator in {"any", "all"} and not isinstance(self.value, list):
            raise ValueError("集合条件须为列表")
        return self


class Selector(Input):
    variant_ids: list[str] = Field(default_factory=list)
    category: str = ""
    series: list[str] = Field(default_factory=list)
    exclude_variant_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def explicit_scope(self):
        if not (self.variant_ids or self.category or self.series):
            raise ValueError("请选择配置、类别或系列作为适用范围")
        return self


class Resource(Input):
    key: Text
    amount: Decimal = Field(ge=0, allow_inf_nan=False)
    unit: Text

    @model_validator(mode="after")
    def unit_known(self):
        if self.unit not in UNITS:
            raise ValueError("资源单位不受支持")
        return self


class KnowledgeInput(Authored):
    name: Text
    kind: Literal["suitability", "accessory", "sharing"]
    status: Literal["draft", "confirmed", "disabled"] = "draft"
    effect: Literal["allow", "deny"] = "allow"
    selector: Selector
    system: str = ""
    role: str = ""
    conditions: list[Condition] = Field(default_factory=list)
    target_variant_ids: list[str] = Field(default_factory=list)
    accessory_type: Literal["required", "recommended", "optional"] = "required"
    mode: Literal["per_unit", "per_capacity", "per_group"] = "per_unit"
    factor: Decimal = Field(default=Decimal(1), gt=0, allow_inf_nan=False)
    shared_roles: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def complete_relation(self):
        if self.kind == "suitability" and not (self.system and self.role):
            raise ValueError("适用关系需要系统和角色")
        if self.kind == "accessory" and not self.target_variant_ids:
            raise ValueError("配件关系需要候选配置")
        if self.kind == "sharing" and len(set(self.shared_roles)) < 2:
            raise ValueError("共享条件至少指定两个系统/角色（例如 无纸化/服务端）")
        return self
