from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from ..common import Authored, Input, Text
from ..evidence import EvidenceReference


class CaseRow(Input):
    id: Text
    section: Text
    name: Text
    model: str = ""
    quantity: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit: str = ""
    raw: dict[str, Annotated[str, StringConstraints(strip_whitespace=False)]] = Field(
        default_factory=dict
    )
    variant_ids: list[Text] = Field(default_factory=list)
    mapping_evidence: str = ""
    evidence_refs: list[EvidenceReference] = Field(min_length=1)
    questions: list[str] = Field(default_factory=list)


class ReferenceCase(Authored):
    name: Text
    rows: list[CaseRow] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_rows(self):
        if len({r.id for r in self.rows}) != len(self.rows):
            raise ValueError("参考案例行标识重复")
        if any(r.variant_ids and not r.mapping_evidence for r in self.rows):
            raise ValueError("配置映射需要明确核对依据，不能按型号自动合并")
        return self


class CaseWrite(Input):
    value: ReferenceCase
    operation_id: Text
    case_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def revision_pair(self):
        if bool(self.case_id) != bool(self.expected_revision):
            raise ValueError("修改案例需要标识及预期修订")
        return self


class RowBinding(Input):
    row_id: Text
    device_ids: list[Text] = Field(default_factory=list)
    requirement_ids: list[Text] = Field(default_factory=list)
    demand_ids: list[Text] = Field(default_factory=list)
    included_allocation_ids: list[Text] = Field(default_factory=list)
    disposition: Literal["compare", "not_enabled", "unresolved"] = "compare"
    feature_system_id: str = ""
    feature: str = ""
    evidence: Text

    @model_validator(mode="after")
    def unique_references(self):
        for identities in (
            self.device_ids,
            self.requirement_ids,
            self.demand_ids,
            self.included_allocation_ids,
        ):
            if len(identities) != len(set(identities)):
                raise ValueError("同一案例行不能重复引用相同对象")
        return self


class CaseReference(Input):
    id: Text
    revision: int = Field(ge=1)
    bindings: list[RowBinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_bindings(self):
        if len({b.row_id for b in self.bindings}) != len(self.bindings):
            raise ValueError("同一案例行请在一个映射中选择多个对象")
        return self


class CaseSet(Input):
    action: Literal["reference_case_set"]
    value: CaseReference | None = None
