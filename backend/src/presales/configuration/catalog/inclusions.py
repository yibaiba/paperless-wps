from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ..common import Input, Text


class IncludedItem(Input):
    id: Text
    name: Text
    variant_id: str | None = None
    kind: Literal["hardware", "software", "license", "accessory"]
    quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    need_keys: list[Text] = Field(default_factory=list)
    status: Literal["draft", "confirmed", "disabled"] = "draft"
    evidence: str = ""

    @model_validator(mode="after")
    def confirmed_basis(self):
        if len(set(self.need_keys)) != len(self.need_keys):
            raise ValueError("同一包含项的配套需求标识不能重复")
        if self.status == "confirmed" and not (
            self.variant_id and self.quantity is not None and self.need_keys and self.evidence
        ):
            raise ValueError("确认已含内容需要具体配置、每单位数量、配套需求标识及原文依据")
        return self
