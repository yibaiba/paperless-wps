from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1)


class ItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    product_id: str
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    group_name: str = Field(min_length=1)
    note: str = ""


class ItemUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    group_name: str = Field(min_length=1)
    note: str = ""
