from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal["pending", "confirmed_variant", "equivalent", "source_error"]


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: ReviewStatus
    actor: str = Field(min_length=1)
    note: str = Field(min_length=1)
    expected_revision: int = Field(ge=0, strict=True)
