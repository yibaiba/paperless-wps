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
    from .gaps import knowledge_gaps

    gaps = knowledge_gaps(definition, package)
    basis_codes = {
        "published_package_missing",
        "role_quantity_missing",
        "role_fulfillment_unconfirmed",
        "role_fulfillment_target_missing",
        "role_definition_unconfirmed",
    }
    return dict(
        supported=not any(g["code"] in basis_codes for g in gaps),
        independent_ready=not any(g["scenario"] == "independent" for g in gaps),
        sharing_evidence_present=any(
            r["kind"] == "sharing" and r["status"] == "confirmed"
            for r in (package or {}).get("rules", [])
        ),
        gaps=gaps,
        recommendations=(package or {}).get("recommendations", []),
    )
