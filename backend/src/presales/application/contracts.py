from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Authored(Input):
    actor: Text
    evidence: Text


class Change(Input):
    expected_revision: int = Field(ge=1)
    payload: dict
