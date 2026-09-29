from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from presales.quotation.schemas import Quotation

from ..catalog.schemas import Attribute
from ..common import Authored, Input, Text
from ..knowledge.schemas import Resource
from .evolution_schemas import AccessoryChoice, SupplyAllocation
from .inclusion_schemas import IncludedAllocation
from .planning.state import GeneratedOrigin, GenerationState
from .role_allocations import RoleAllocation


class Room(Input):
    id: Text
    name: Text


class System(Input):
    inputs: list[Attribute] = Field(default_factory=list)
    definition_id: str = ""
    knowledge_package_id: str = ""
    features: list[str] = Field(default_factory=list)
    id: Text
    room_id: str | None = None
    name: Text
    kind: Text

    @model_validator(mode="after")
    def unique_inputs(self):
        if len({a.key for a in self.inputs}) != len(self.inputs):
            raise ValueError("同一系统的项目输入名称不能重复")
        return self


class EnvironmentParameter(Attribute):
    purpose: Literal["product_requirement", "project_input"] = "product_requirement"


class Requirement(Input):
    allocations: list[RoleAllocation] = Field(default_factory=list)
    role_id: str = ""
    id: Text
    system_id: Text
    role: Text
    environment: list[EnvironmentParameter] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    device_id: str | None = None


class Deployment(Input):
    generated_origin: GeneratedOrigin | None = None
    id: Text
    name: Text
    variant_id: Text
    source_id: Text
    quantity: Decimal = Field(default=1, gt=0, allow_inf_nan=False)
    kind: Literal["hardware", "software", "license", "accessory"] = "hardware"
    note: str = ""
    variant_snapshot: dict | None = None
    source_snapshot: dict | None = None
    origin_suggestion: str | None = None


class AccessoryAllocation(Input):
    id: Text
    demand_id: Text
    device_id: Text
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    evidence: Text


class Configuration(Authored):
    generation: GenerationState = Field(default_factory=GenerationState)
    room_inputs: dict[str, list[Attribute]] = Field(default_factory=dict)
    project_inputs: list[Attribute] = Field(default_factory=list)
    included_allocations: list[IncludedAllocation] = Field(default_factory=list)
    quotation: Quotation | None = None
    calculation_version: Literal[1, 2, 3] = 1
    definition_snapshot_id: str | None = None
    accessory_choices: list[AccessoryChoice] = Field(default_factory=list)
    supply_allocations: list[SupplyAllocation] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    systems: list[System] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    devices: list[Deployment] = Field(default_factory=list)
    accessory_allocations: list[AccessoryAllocation] = Field(default_factory=list)
    drawing_xml: str = ""
    knowledge_snapshot: list[dict] | None = None
    knowledge_snapshot_id: str | None = None

    @model_validator(mode="after")
    def references(self):
        for items in (
            self.rooms,
            self.systems,
            self.requirements,
            self.devices,
            self.accessory_allocations,
            self.included_allocations,
            self.supply_allocations,
        ):
            if len({i.id for i in items}) != len(items):
                raise ValueError("同类对象标识不能重复")
        if self.included_allocations and self.calculation_version != 3:
            raise ValueError("已含内容抵扣需要先预览并升级至计算语义版本 3")
        rooms, systems = {r.id for r in self.rooms}, {s.id for s in self.systems}
        if self.room_inputs.keys() - rooms:
            raise ValueError("房间输入引用了不存在的房间")
        for inputs in [self.project_inputs, *self.room_inputs.values()]:
            if len({a.key for a in inputs}) != len(inputs):
                raise ValueError("范围输入不能包含重复参数")
        devices = {d.id: d for d in self.devices}
        if any(s.room_id and s.room_id not in rooms for s in self.systems):
            raise ValueError("系统引用的房间不存在")
        if any(r.system_id not in systems for r in self.requirements):
            raise ValueError("角色引用的系统不存在")
        for requirement in self.requirements:
            if requirement.allocations:
                if self.calculation_version != 3:
                    raise ValueError("角色数量分配需要计算语义版本 3")
                if requirement.device_id:
                    raise ValueError("角色单设备关联与数量分配不能同时填写")
                ids = [a.device_id for a in requirement.allocations]
                if len(set(ids)) != len(ids) or set(ids) - devices.keys():
                    raise ValueError("角色分配设备重复或不存在")
            if requirement.device_id and requirement.device_id not in devices:
                raise ValueError("角色关联的实际设备不存在")
        for device in self.devices:
            count = sum(r.device_id == device.id for r in self.requirements)
            if count > 1 and device.quantity != 1:
                raise ValueError("共用设备请按单台实例维护，再关联多个角色")
        if any(item.device_id not in devices for item in self.included_allocations):
            raise ValueError("已含内容抵扣引用的宿主设备不存在")
        if any(item.device_id not in devices for item in self.accessory_allocations):
            raise ValueError("配套分配引用的设备不存在")
        if len({c.demand_id for c in self.accessory_choices}) != len(self.accessory_choices):
            raise ValueError("同一配套需求不能重复设置选用状态")
        if any(item.device_id not in devices for item in self.supply_allocations):
            raise ValueError("供货分配引用的设备不存在")
        return self


class ConfigurationSave(Input):
    expected_revision: int = Field(ge=0)
    configuration: Configuration


class CandidateRequest(Input):
    calculation_version: Literal[1, 2, 3] = 1
    system_definition_id: str = ""
    role_id: str = ""
    definition_snapshot_id: str | None = None
    knowledge_package_id: str = ""
    system: str = ""
    role: str = ""
    environment: list[EnvironmentParameter] = Field(default_factory=list)
    knowledge_snapshot_id: str | None = None
    include_all: bool = False
    mode: Literal["known", "semantic", "all"] = "known"
    query_text: str = ""
    limit: int = Field(default=30, ge=1, le=100)

    @model_validator(mode="after")
    def semantic_query(self):
        if (
            self.mode != "all"
            and not self.include_all
            and (not self.system.strip() or not self.role.strip())
        ):
            raise ValueError("按角色筛选需要系统和角色；未关联设备请使用全部产品模式")
        if self.mode == "semantic" and not self.query_text:
            raise ValueError("智能查找需要填写需求描述")
        return self


class CheckRequest(Input):
    configuration: Configuration
    refresh_knowledge: bool = False
    upgrade_calculation: bool = False


class SuggestionApply(CheckRequest):
    fingerprint: Text
    suggestion_id: Text
    variant_id: str | None = None
    source_id: str | None = None
    existing_device_id: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    supply_source: Literal["purchase", "existing", "unknown"] = "unknown"
    supply_evidence: str = ""

    @model_validator(mode="after")
    def one_target(self):
        new_device = bool(self.variant_id or self.source_id)
        if new_device and not (self.variant_id and self.source_id):
            raise ValueError("新增配套必须同时选择配置和资料来源")
        if new_device == bool(self.existing_device_id):
            raise ValueError("请选择新增配套或关联一个已有设备")
        return self
