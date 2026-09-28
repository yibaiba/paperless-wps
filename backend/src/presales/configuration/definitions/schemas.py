from typing import Literal

from pydantic import Field, model_validator

from ..common import Authored, Input, Text
from ..knowledge.schemas import Selector


class RoleDefinition(Input):
    id: Text
    name: Text
    required: bool = True
    feature: str = ""
    capability_ids: list[str] = Field(default_factory=list)


class SystemDefinition(Authored):
    name: Text
    status: Literal["draft", "confirmed"] = "draft"
    legacy_names: list[str] = Field(default_factory=list)
    roles: list[RoleDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_roles(self):
        if len({r.id for r in self.roles}) != len(self.roles):
            raise ValueError("角色标识不能重复")
        if self.status == "confirmed" and not self.roles:
            raise ValueError("确认系统需求定义前请维护角色")
        return self


class Member(Input):
    id: Text
    revision: int = Field(ge=1)


class Coverage(Input):
    role_id: Text
    selector: Selector
    accessories: Literal["unreviewed", "needs_review", "complete", "none"] = "unreviewed"
    resources: Literal["unknown", "required", "not_applicable"] = "unknown"
    evidence: Text


class KnowledgePackage(Authored):
    name: Text
    system_definition_id: Text
    definition_revision: int = Field(ge=1)
    branch: Text
    status: Literal["draft", "published"] = "draft"
    members: list[Member] = Field(default_factory=list)
    coverage: list[Coverage] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_members(self):
        if len({m.id for m in self.members}) != len(self.members):
            raise ValueError("知识包不能重复引用同一关系")
        return self


class Capability(Authored):
    name: Text
    description: str = ""
