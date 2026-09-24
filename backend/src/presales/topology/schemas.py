from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Position(Input):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class SystemGroup(Input):
    id: Text
    name: Text
    product_line: str = ""
    position: Position
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)


class Device(Input):
    id: Text
    product_id: Text
    position: Position
    quantity: Positive = Decimal(1)
    group_id: str | None = None
    role: str = ""
    serves_group_ids: list[Text] = Field(default_factory=list)
    note: str = ""


class Relation(Input):
    id: Text
    source: Text
    target: Text
    kind: Literal["required", "optional", "connection", "unconfirmed"] = "unconfirmed"
    mode: Literal["per_unit", "per_capacity", "per_group"] = "per_unit"
    factor: Positive = Decimal(1)
    evidence: str = ""
    source_port: str = ""
    target_port: str = ""
    cable: str = ""
    length_m: Positive | None = None


class TopologyInput(Input):
    name: Text
    actor: Text
    drawing_xml: Text | None = None
    groups: list[SystemGroup] = Field(default_factory=list)
    devices: list[Device] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def read_drawing(cls, values):
        if isinstance(values, dict) and values.get("drawing_xml"):
            from .drawio.service import business_data

            # XML is authoritative: quantities and links cannot disagree with the saved drawing.
            return {**values, **business_data(values["drawing_xml"])}
        return values

    @model_validator(mode="after")
    def references(self):
        all_ids = [
            item.id for items in (self.groups, self.devices, self.relations) for item in items
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("设备、系统分组及关系的标识不能重复")
        groups = {g.id for g in self.groups}
        devices = {d.id for d in self.devices}
        if len({g.name for g in self.groups}) != len(self.groups):
            raise ValueError("系统分组名称不能重复，请使用不同房间或系统名称")
        for device in self.devices:
            self.validate_device_groups(device, groups)
        for relation in self.relations:
            if relation.source not in devices or relation.target not in devices:
                raise ValueError("连线两端必须是图中存在的设备")
            if relation.source == relation.target:
                raise ValueError("关系不能连接设备自身")
        return self

    @staticmethod
    def validate_device_groups(device: Device, groups: set[str]):
        referenced = set(device.serves_group_ids)
        if device.group_id is not None:
            referenced.add(device.group_id)
        if not referenced <= groups:
            raise ValueError("设备引用的系统分组不存在")
        if len(device.serves_group_ids) != len(set(device.serves_group_ids)):
            raise ValueError("服务系统不能重复")


class TopologyUpdate(TopologyInput):
    expected_revision: int = Field(ge=1, strict=True)


class ConvertInput(Input):
    expected_revision: int = Field(ge=1, strict=True)
    actor: Text
