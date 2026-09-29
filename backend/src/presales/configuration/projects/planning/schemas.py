from typing import Literal

from pydantic import Field

from ...catalog.schemas import Attribute
from ...common import Input, Text
from ...knowledge.schemas import Resource
from ..schemas import EnvironmentParameter, Room, System
from .state import GenerationState


class RoleInput(Input):
    role_id: Text
    environment: list[EnvironmentParameter] | None = None
    resources: list[Resource] | None = None


class SystemInput(Input):
    system: System
    roles: list[RoleInput] = Field(default_factory=list)
    features_confirmed: bool = False


class RequirementsPatch(Input):
    action: Literal["requirements_patch"]
    rooms: list[Room] = Field(default_factory=list)
    systems: list[SystemInput] = Field(default_factory=list)
    generation: GenerationState | None = None
    room_inputs: dict[str, list[Attribute]] | None = None
    project_inputs: list[Attribute] | None = None


class ProposalApply(Input):
    action: Literal["proposal_apply"]
    proposal_id: Text
    option_id: Text
    fingerprint: Text
    remove_device_ids: list[Text] = Field(default_factory=list)
