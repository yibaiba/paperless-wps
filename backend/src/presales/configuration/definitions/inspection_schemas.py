"""Versioned, reusable resource checks; compatibility remains separate knowledge."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ..catalog.schemas import UNITS
from ..common import Authored, Input, Text


class InspectionMetric(Input):
    key: Text
    label: Text
    input_key: Text
    input_label: Text
    input_unit: Text
    unit: Text
    aggregation: Literal["sum", "max"] = "sum"
    capacity_basis: Literal["deployment", "unit"] = "deployment"
    factor: Decimal = Field(default=1, gt=0, allow_inf_nan=False)
    applies_to: Literal["selected_device", "accessory"] = "selected_device"
    target_need_key: str = ""

    @model_validator(mode="after")
    def valid_metric(self):
        if self.unit not in UNITS or self.input_unit not in UNITS:
            raise ValueError("检查指标单位不受支持")
        if (self.applies_to == "accessory") != bool(self.target_need_key):
            raise ValueError("配套承担的指标必须指定配套需求，当前设备指标不能指定配套需求")
        return self


class InspectionProfile(Authored):
    name: Text
    status: Literal["draft", "confirmed", "disabled"] = "draft"
    selected_device_policy: Literal["unknown", "required", "not_applicable"] = "unknown"
    metrics: list[InspectionMetric] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_profile(self):
        identities = [(m.key, m.applies_to, m.target_need_key) for m in self.metrics]
        if len(identities) != len(set(identities)):
            raise ValueError("同一承担对象的检查指标不能重复")
        units = {}
        for metric in self.metrics:
            if metric.input_key in units and units[metric.input_key] != metric.input_unit:
                raise ValueError("同一输入不能使用不同单位")
            units[metric.input_key] = metric.input_unit
        direct = any(m.applies_to == "selected_device" for m in self.metrics)
        if self.selected_device_policy == "not_applicable" and direct:
            raise ValueError("当前设备不涉及容量时，指标只能由配套设备承担")
        if self.status == "confirmed":
            if self.selected_device_policy == "unknown":
                raise ValueError("确认前请明确当前设备是否需要容量检查")
            if self.selected_device_policy == "required" and not direct:
                raise ValueError("确认需要容量检查时请定义当前设备的指标")
        return self
