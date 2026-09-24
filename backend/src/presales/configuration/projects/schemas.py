from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ..catalog.schemas import Attribute
from ..common import Authored, Input, Text
from ..knowledge.schemas import Resource


class Room(Input):
    id: Text
    name: Text


class System(Input):
    id: Text
    room_id: str | None = None
    name: Text
    kind: Text


class Requirement(Input):
    id: Text
    system_id: Text
    role: Text
    environment: list[Attribute] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    device_id: str | None = None


class Deployment(Input):
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
    calculation_version: Literal[1, 2] = 1
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
        ):
            if len({i.id for i in items}) != len(items):
                raise ValueError("同类对象标识不能重复")
        rooms, systems = {r.id for r in self.rooms}, {s.id for s in self.systems}
        devices = {d.id: d for d in self.devices}
        if any(s.room_id and s.room_id not in rooms for s in self.systems):
            raise ValueError("系统引用的房间不存在")
        if any(r.system_id not in systems for r in self.requirements):
            raise ValueError("角色引用的系统不存在")
        for requirement in self.requirements:
            if requirement.device_id and requirement.device_id not in devices:
                raise ValueError("角色关联的实际设备不存在")
        for device in self.devices:
            count = sum(r.device_id == device.id for r in self.requirements)
            if count > 1 and device.quantity != 1:
                raise ValueError("共用设备请按单台实例维护，再关联多个角色")
        if any(item.device_id not in devices for item in self.accessory_allocations):
            raise ValueError("配套分配引用的设备不存在")
        return self


class ConfigurationSave(Input):
    expected_revision: int = Field(ge=0)
    configuration: Configuration


class CandidateRequest(Input):
    system: Text
    role: Text
    environment: list[Attribute] = Field(default_factory=list)


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

    @model_validator(mode="after")
    def one_target(self):
        new_device = bool(self.variant_id or self.source_id)
        if new_device and not (self.variant_id and self.source_id):
            raise ValueError("新增配套必须同时选择配置和资料来源")
        if new_device == bool(self.existing_device_id):
            raise ValueError("请选择新增配套或关联一个已有设备")
        return self
