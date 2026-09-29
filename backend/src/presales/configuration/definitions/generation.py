"""Reviewed generation knowledge, pinned inside existing definitions and packages."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ..catalog.schemas import UNITS
from ..common import Authored, Text
from ..knowledge.schemas import Condition, EvidenceReference


class RoleQuantity(Authored):
    status: Literal["draft", "confirmed"] = "draft"
    scope: Literal["system", "room", "project"] = "system"
    input_key: str = ""
    input_unit: str = ""
    mode: Literal["per_unit", "per_capacity", "per_group"] | None = None
    factor: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def complete(self):
        if self.input_unit and self.input_unit not in UNITS:
            raise ValueError("角色数量输入单位不受支持")
        if self.status == "confirmed" and (
            not self.mode
            or self.factor is None
            or (self.mode != "per_group" and not self.input_key)
        ):
            raise ValueError("确认角色数量需要计算方式、系数及数量输入；固定数量使用范围内固定数量")
        return self


class RoleFulfillment(Authored):
    status: Literal["draft", "confirmed"] = "draft"
    role_id: Text
    need_key: Text
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class Recommendation(Authored):
    role_id: Text
    need_key: str = ""
    status: Literal["draft", "confirmed"] = "draft"
    variant_ids: list[Text] = Field(min_length=1)
    conditions: list[Condition] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.variant_ids)) != len(self.variant_ids):
            raise ValueError("推荐顺序不能重复列出同一配置")
        return self


def generation_coverage(definition, package):
    gaps = []
    if not package or package.get("status") != "published":
        gaps.append(dict(code="published_package_missing", field="knowledge_package_id"))
    for role in definition["roles"]:
        quantity, fulfillment = role.get("quantity_basis"), role.get("fulfilled_by")
        if not fulfillment and (not quantity or quantity.get("status") != "confirmed"):
            gaps.append(
                dict(code="role_quantity_missing", role_id=role["id"], field="quantity_basis")
            )
        if fulfillment and fulfillment.get("status") != "confirmed":
            gaps.append(
                dict(code="role_fulfillment_unconfirmed", role_id=role["id"], field="fulfilled_by")
            )
    return dict(
        supported=not gaps, gaps=gaps, recommendations=(package or {}).get("recommendations", [])
    )
