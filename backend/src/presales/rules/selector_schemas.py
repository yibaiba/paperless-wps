from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from presales.catalog.attributes.schemas import AttributeKey, AttributeValue


class AttributeCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: AttributeKey
    operator: Literal["any", "all"] = "all"
    values: list[AttributeValue] = Field(min_length=1)


class SourceSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    import_id: AttributeValue
    conditions: list[AttributeCondition] = Field(min_length=1)
    exclude_product_ids: list[AttributeValue] = Field(default_factory=list)
