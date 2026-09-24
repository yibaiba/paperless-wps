from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .selector_schemas import SourceSelector


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1)
    source_product_id: str | None = Field(default=None, min_length=1)
    source_selector: SourceSelector | None = None
    additional_source_ids: list[str] = Field(default_factory=list)
    target_product_id: str = Field(min_length=1)
    alternative_target_ids: list[str] = Field(default_factory=list)
    relation: Literal["quantity", "required", "choice"] = "quantity"
    mode: Literal["per_capacity", "per_unit", "per_group"]
    factor: Decimal = Field(gt=0, allow_inf_nan=False)
    status: Literal["draft", "active", "disabled"] = "draft"
    evidence: str = Field(min_length=1)
    actor: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_products(self):
        if self.source_selector is not None:
            if self.source_product_id or self.additional_source_ids:
                raise ValueError("按属性匹配与指定触发型号不能同时使用")
        elif not self.source_product_id:
            raise ValueError("请选择触发型号或填写属性匹配条件")
        sources = (
            [self.source_product_id] if self.source_product_id else []
        ) + self.additional_source_ids
        targets = [self.target_product_id, *self.alternative_target_ids]
        for values in (sources, targets):
            if any(not value.strip() for value in values) or len(set(values)) != len(values):
                raise ValueError("产品记录不能为空或重复")
        if set(sources) & set(targets):
            raise ValueError("触发产品和配套产品不能重叠")
        if (self.relation == "choice") != bool(self.alternative_target_ids):
            raise ValueError("人工选择关系需要至少两个候选；其他关系不使用候选产品")
        return self


class RuleUpdate(RuleInput):
    expected_revision: int = Field(ge=1, strict=True)


class TrialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: Decimal = Field(ge=0, allow_inf_nan=False)


class ApplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: str = Field(min_length=1)
    suggestion_ids: list[str] = Field(min_length=1)
