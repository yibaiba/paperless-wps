"""Explicit local edits; publication and knowledge refresh are not workbook edits."""

from typing import Annotated, Literal

from pydantic import Field

from presales.configuration.common import Input, Text
from presales.configuration.projects.edit_schemas import (
    AccessoryChoice,
    AccessoryLink,
    AccessoryRemove,
    IncludedLink,
    IncludedRemove,
    RequirementPut,
    RequirementsPatch,
    RoomPut,
    SupplySet,
    SystemPut,
    SystemSetupOperation,
)


class RequirementRemove(Input):
    action: Literal["remove"]
    collection: Literal["requirements"]
    id: Text


BusinessOperation = Annotated[
    RoomPut
    | SystemPut
    | RequirementPut
    | RequirementsPatch
    | SystemSetupOperation
    | SupplySet
    | AccessoryLink
    | AccessoryRemove
    | AccessoryChoice
    | IncludedLink
    | IncludedRemove
    | RequirementRemove,
    Field(discriminator="action"),
]


class BusinessScope(Input):
    sheet: Text
    start_row: int = Field(ge=1)
    end_row: int = Field(ge=1)
    room_id: str | None = None
    system_id: Text
    requirement_id: str | None = None


class CompletionCell(Input):
    sheet: Text
    row: int = Field(ge=1)
    column: int = Field(ge=1)
    values: dict[str, str] = Field(default_factory=dict)
    formula_fields: list[str] = Field(default_factory=list)
    merged_fields: list[str] = Field(default_factory=list)


class RecentEdit(Input):
    operation_id: Text
    kind: Literal["accept", "replace", "quantity", "remove", "undo", "dismiss"]
    suggestion_id: str | None = None
    device_id: str | None = None
    requirement_id: str | None = None


class CompletionLocation(Input):
    local_revision: int = Field(ge=0)
    scope: BusinessScope
    active_cell: CompletionCell
    query: str = ""
    target_cells: list[CompletionCell] = Field(default_factory=list)
    recent_edits: list[RecentEdit] = Field(default_factory=list)
