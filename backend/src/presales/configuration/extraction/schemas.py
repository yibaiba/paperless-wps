from typing import Literal

from pydantic import Field

from ..common import Authored, Input, Text


class MaterialInput(Input):
    name: Text
    text: Text


class JobInput(Authored):
    product_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    variant_ids: list[str] = Field(default_factory=list)


class Draft(Input):
    kind: Literal["product", "variant", "source_link", "knowledge", "question"]
    quotation: Text
    proposal: dict
    target_id: str | None = None
    expected_revision: int = Field(default=0, ge=0)


class ModelOutput(Input):
    drafts: list[Draft]


class Decision(Authored):
    draft_ids: list[Text] = Field(min_length=1)
    action: Literal["accept", "reject"]


class DraftEdit(Input):
    expected_revision: int = Field(ge=1)
    draft: Draft
