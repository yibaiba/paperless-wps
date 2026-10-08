from pydantic import Field

from presales.configuration.common import Input, Text
from presales.configuration.projects.edit_schemas import Operation
from presales.lists.schemas import DraftWrite


class CreateDraft(Input):
    project_id: Text
    expected_revision: int = Field(ge=0)
    operation_id: Text


class EditDraft(DraftWrite):
    operations: list[Operation] = Field(min_length=1)


class RestoreDraft(DraftWrite):
    checkpoint_revision: int = Field(ge=1)


class PreviewDraft(Input):
    expected_revision: int = Field(ge=1)
    draft_version: int = Field(ge=0)
    operations: list[Operation] = Field(min_length=1)


class RecheckDraft(DraftWrite):
    expected_project_revision: int = Field(ge=0)
    fingerprint: Text
    refresh_knowledge: bool = False
    upgrade_calculation: bool = False
    upgrade_decisions: bool = False
    cleanup_allocations: bool = False
