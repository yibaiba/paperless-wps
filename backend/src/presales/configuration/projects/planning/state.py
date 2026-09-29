from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ...common import Input, Text


class RequirementSource(Input):
    id: Text
    object_id: Text
    field: Text
    kind: Literal["customer", "document", "agent_interpretation"]
    confirmed: bool = False
    quote: Text
    locator: str = ""


class SelectionPreference(Input):
    requirement_id: Text
    required_variant_id: str = ""
    excluded_variant_ids: list[Text] = Field(default_factory=list)
    reusable_device_ids: list[Text] = Field(default_factory=list)
    source_id: str = ""
    evidence: Text

    @model_validator(mode="after")
    def no_contradiction(self):
        if self.required_variant_id in self.excluded_variant_ids:
            raise ValueError("同一配置不能同时被指定和排除")
        return self


class GenerationState(Input):
    sources: list[RequirementSource] = Field(default_factory=list)
    preferences: list[SelectionPreference] = Field(default_factory=list)
    features_confirmed: list[Text] = Field(default_factory=list)
    supply_source: Literal["purchase", "unknown"] = "unknown"
    supply_evidence: str = ""
    budget: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    budget_evidence: str = ""

    @model_validator(mode="after")
    def explicit(self):
        if self.supply_source == "purchase" and not self.supply_evidence:
            raise ValueError("明确新增采购需要需求依据")
        if self.budget is not None and not self.budget_evidence:
            raise ValueError("预算约束需要客户依据")
        if len({p.requirement_id for p in self.preferences}) != len(self.preferences):
            raise ValueError("同一角色不能重复设置选型偏好")
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError("需求来源标识不能重复")
        return self


class GeneratedOrigin(Input):
    key: Text
    proposal_id: Text
    variant_locked: bool = False
    quantity_locked: bool = False
