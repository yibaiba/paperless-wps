from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

AttributeKey = Literal["series", "functions", "interfaces", "systems"]
AttributeValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AttributeValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    series: list[AttributeValue] = Field(default_factory=list)
    functions: list[AttributeValue] = Field(default_factory=list)
    interfaces: list[AttributeValue] = Field(default_factory=list)
    systems: list[AttributeValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_values(self):
        if any(len(values) != len(set(values)) for values in self.model_dump().values()):
            raise ValueError("同一属性不能重复填写同一个值")
        return self


class AttributeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    values: AttributeValues
    expected_revision: int = Field(ge=0, strict=True)
    actor: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class AttributeSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: AttributeValue
    expected_revision: int = Field(ge=0, strict=True)


class AttributeBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    items: list[AttributeSelection] = Field(min_length=1)
    field: AttributeKey
    values: list[AttributeValue] = Field(min_length=1)
    operation: Literal["add", "remove"]
    actor: str = Field(min_length=1)
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_products(self):
        if len({i.product_id for i in self.items}) != len(self.items):
            raise ValueError("批量维护不能重复选择产品")
        return self
