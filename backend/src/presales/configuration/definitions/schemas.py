from typing import Literal

from pydantic import Field, model_validator

from ..common import Authored, Input, Text
from ..knowledge.schemas import Selector
from .generation import Recommendation, RoleFulfillment, RoleQuantity


class InspectionReference(Input):
    id: Text
    revision: int = Field(ge=1)


class RoleDefinition(Input):
    quantity_basis: RoleQuantity | None = None
    fulfilled_by: RoleFulfillment | None = None
    output_kind: Literal["hardware", "software", "license", "accessory"] = "hardware"
    inspection_profile: InspectionReference | None = None
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
        for role in self.roles:
            if role.fulfilled_by and (
                role.fulfilled_by.role_id == role.id
                or role.fulfilled_by.role_id not in {r.id for r in self.roles}
            ):
                raise ValueError("配套满足关系必须引用此系统的其他角色")
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
    recommendations: list[Recommendation] = Field(default_factory=list)
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
