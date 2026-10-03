from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from presales.configuration.common import Authored, Input, Text
from presales.configuration.projects.edit_schemas import Operation


class Page(Input):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, gt=0)


class SystemsList(Page):
    definition_id: str = ""
    knowledge_package_id: str = ""
    definition_snapshot_id: str | None = None
    knowledge_snapshot_id: str | None = None
    features: list[str] = Field(default_factory=list)


class CreateList(Authored):
    name: Text
    operation_id: Text
    project_id: str | None = None
    revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def base_revision(self):
        if bool(self.project_id) != bool(self.revision):
            raise ValueError("复制项目需要同时指定项目 ID 和保存修订")
        return self


class DraftWrite(Input):
    draft_id: Text
    expected_revision: int = Field(ge=1)
    operation_id: Text


class PlanList(DraftWrite):
    proposal_id: str | None = None
    option_offset: int = Field(default=0, ge=0)
    deployment: Literal["independent", "shared"] = "independent"


class UpdateList(DraftWrite):
    operations: list[Operation] = Field(min_length=1)


class CheckList(DraftWrite):
    refresh_knowledge: bool = False
    upgrade_calculation: bool = False
    upgrade_decisions: bool = False


class SaveList(DraftWrite):
    expected_project_revision: int = Field(ge=0)
    fingerprint: Text


class ExportList(Input):
    project_id: Text
    revision: int = Field(ge=1)
    output: Literal["configuration", "quotation", "both"] = "both"
    operation_id: Text


class GetList(Page):
    proposal_id: str | None = None
    option_id: str | None = None
    draft_id: str | None = None
    project_id: str | None = None
    revision: int | None = Field(default=None, ge=1)
    price_adoption_date: date | None = None
    view: Literal[
        "proposals",
        "proposal_lines",
        "proposal_questions",
        "proposal_decisions",
        "proposal_changes",
        "summary",
        "price_updates",
        "devices",
        "procurement",
        "quotation",
        "issues",
        "evidence",
        "changes",
        "requirements",
        "allocations",
        "template",
    ] = "summary"

    @model_validator(mode="after")
    def one_identity(self):
        if bool(self.draft_id) == bool(self.project_id):
            raise ValueError("请选择草稿 ID 或项目 ID")
        return self


class CatalogSearch(Page):
    query: str = ""
    draft_id: str | None = None
    requirement_id: str | None = None
    include_other_products: bool = False


class CatalogGet(Input):
    on_date: date | None = None
    variant_id: Text
    draft_id: str | None = None


class ListSearch(Page):
    query: str = ""
    project_id: str | None = None
