from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ..catalog.schemas import UNITS
from ..common import Authored, Input, Text


class Condition(Input):
    field: Text
    operator: Literal["eq", "any", "all", "range"]
    value: str | list[str] | None = None
    minimum: Decimal | None = Field(default=None, allow_inf_nan=False)
    maximum: Decimal | None = Field(default=None, allow_inf_nan=False)
    unit: str = ""

    @model_validator(mode="after")
    def complete(self):
        if self.unit and self.unit not in UNITS:
            raise ValueError("条件单位不受支持")
        if self.operator == "range":
            if self.minimum is None and self.maximum is None:
                raise ValueError("范围条件至少填写一个边界")
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise ValueError("下限不能大于上限")
        elif self.value is None:
            raise ValueError("请填写条件值")
        if self.operator in {"any", "all"} and not isinstance(self.value, list):
            raise ValueError("集合条件须为列表")
        return self


class Selector(Input):
    variant_ids: list[str] = Field(default_factory=list)
    category: str = ""
    series: list[str] = Field(default_factory=list)
    exclude_variant_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def explicit_scope(self):
        if not (self.variant_ids or self.category or self.series):
            raise ValueError("请选择配置、类别或系列作为适用范围")
        return self


class Resource(Input):
    aggregation: Literal["sum", "max"] = "sum"
    capacity_basis: Literal["deployment", "unit"] = "deployment"
    key: Text
    amount: Decimal = Field(ge=0, allow_inf_nan=False)
    unit: Text
    applies_to: Literal["selected_device", "accessory"] = "selected_device"
    target_need_key: str = ""

    @model_validator(mode="after")
    def unit_known(self):
        if self.unit not in UNITS:
            raise ValueError("资源单位不受支持")
        if self.applies_to == "accessory" and not self.target_need_key:
            raise ValueError("配套资源必须指定需求标识，例如 server")
        if self.applies_to == "selected_device" and self.target_need_key:
            raise ValueError("当前配置资源不能指定配套需求标识")
        return self


class EvidenceReference(Input):
    source_id: Text
    locator: Text
    quote: Text


class SharedRole(Input):
    system_definition_id: Text
    role_id: Text


class KnowledgeInput(Authored):
    schema_version: Literal[1, 2] = 1
    identity_mapping: dict | None = None
    system_definition_id: str = ""
    role_id: str = ""
    activation_conditions: list[Condition] = Field(default_factory=list)
    alternative_group: str = ""
    quantity_review: Literal["unreviewed", "confirmed"] = "unreviewed"
    quantity_evidence: str = ""
    resource_policy: Literal["unknown", "required", "not_applicable"] = "unknown"
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    shared_role_refs: list[SharedRole] = Field(default_factory=list)
    scope_basis: Literal["listed_configurations", "entire_scope"] = "listed_configurations"
    reviewed_variant_ids: list[str] = Field(default_factory=list)
    completion: Literal["complete", "incomplete"] | None = Field(default=None, exclude=True)
    missing_fields: list[str] = Field(default_factory=list, exclude=True)
    name: Text
    kind: Literal["suitability", "accessory", "sharing"]
    status: Literal["draft", "confirmed", "disabled"] = "draft"
    effect: Literal["allow", "deny"] = "allow"
    selector: Selector
    system: str = ""
    role: str = ""
    conditions: list[Condition] = Field(default_factory=list)
    need_key: str = ""
    need_name: str = ""
    target_variant_ids: list[str] = Field(default_factory=list)
    accessory_type: Literal["required", "recommended", "optional"] = "required"
    calculation_scope: Literal["device", "system", "room", "project"] | None = "device"
    quantity_source: Literal["device_quantity", "environment"] = "device_quantity"
    quantity_key: str = ""
    quantity_unit: str = ""
    mode: Literal["per_unit", "per_capacity", "per_group"] | None = "per_unit"
    factor: Decimal | None = Field(default=Decimal(1), gt=0, allow_inf_nan=False)
    output_kind: Literal["hardware", "software", "license", "accessory"] = "accessory"
    allocation_mode: Literal["consumable", "shareable"] = "consumable"
    shared_roles: list[str] = Field(default_factory=list)
    migration_source: dict | None = None

    @model_validator(mode="after")
    def complete_relation(self):
        if self.quantity_unit and self.quantity_unit not in UNITS:
            raise ValueError("数量输入单位不受支持")
        if self.schema_version == 2:
            for key in ("calculation_scope", "mode", "factor"):
                if key not in self.model_fields_set:
                    setattr(self, key, None)
            if self.quantity_review == "confirmed" and (
                not self.quantity_evidence or accessory_missing_fields(self)
            ):
                raise ValueError("确认数量需要完整公式、候选及数量依据")
            if self.alternative_group and self.kind != "suitability":
                raise ValueError("替代分支仅用于系统适用关系")
        if self.kind == "suitability" and not (
            (self.system and self.role) or (self.system_definition_id and self.role_id)
        ):
            raise ValueError("适用关系需要系统和角色")
        if self.kind == "accessory" and self.status == "confirmed" and self.schema_version == 1:
            missing = accessory_missing_fields(self)
            if missing:
                raise ValueError("已确认配套缺少：" + "、".join(missing))
        if (
            self.kind == "sharing"
            and max(
                len(set(self.shared_roles)),
                len({(r.system_definition_id, r.role_id) for r in self.shared_role_refs}),
            )
            < 2
        ):
            raise ValueError("共享条件至少指定两个系统/角色（例如 无纸化/服务端）")
        return self


def accessory_missing_fields(data: KnowledgeInput | dict) -> list[str]:
    value = data if isinstance(data, dict) else data.model_dump(mode="json")
    if value.get("kind") != "accessory":
        return []
    missing = []
    if not value.get("target_variant_ids"):
        missing.append("候选配置")
    if not value.get("calculation_scope"):
        missing.append("计算范围")
    if not value.get("mode") or value.get("factor") is None:
        missing.append("数量公式")
    if value.get("quantity_source") == "environment" and not value.get("quantity_key"):
        missing.append("需求参数")
    return missing


def with_completion(view: dict) -> dict:
    missing = accessory_missing_fields(view)
    if view.get("kind") == "accessory" and view.get("schema_version") == 2:
        if view.get("quantity_review") != "confirmed":
            missing.append("数量依据待确认")
    return {
        **view,
        "completion": "incomplete" if missing else "complete",
        "missing_fields": missing,
    }
