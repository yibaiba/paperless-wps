from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from presales.catalog.parser import PRICE_HEADERS
from presales.configuration.catalog.schemas import ProductInput, VariantInput
from presales.configuration.common import Authored, Input, Text


class PriceChange(Input):
    column: Text
    state: Literal["amount", "inquiry", "keep", "skip"]
    amount: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    effective_date: date

    @model_validator(mode="after")
    def valid_price(self):
        if self.column not in PRICE_HEADERS:
            raise ValueError("请选择现有价格列")
        if (self.state == "amount") != (self.amount is not None):
            raise ValueError("金额状态须填写单价；待询价或沿用原价不得填写金额")
        return self


class Decision(Authored):
    action: Literal["prices", "display", "correct", "new_variant", "new_product", "supply", "defer"]
    manual_unit: str = ""
    manual_specification: str = ""
    variant_id: str = ""
    expected_variant_revision: int = Field(default=0, ge=0)
    variant: VariantInput | None = None
    product: ProductInput | None = None
    prices: list[PriceChange] = Field(default_factory=list)
    supply_status: Literal["available", "discontinued", "not_for_sale"] | None = None
    replacements: list[str] = Field(default_factory=list)
    copy_rule_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_columns(self):
        columns = [p.column for p in self.prices]
        if len(set(columns)) != len(columns):
            raise ValueError("一行同一价格列只能处理一次")
        return self


class CreateBatch(Authored):
    name: Text
    import_id: str | None = None
    baseline_import_id: str | None = None
    sheets: list[str] = Field(default_factory=list)
    variant_ids: list[str] = Field(default_factory=list)
    operation_id: Text


class RowEdit(Input):
    row_id: Text
    decision: Decision


class EditBatch(Input):
    expected_revision: int = Field(ge=1)
    edits: list[RowEdit] = Field(min_length=1)
    operation_id: Text


class PreviewBatch(Input):
    expected_revision: int = Field(ge=1)
    row_ids: list[str] = Field(min_length=1)


class ApplyBatch(PreviewBatch):
    fingerprint: Text
    operation_id: Text


class PriceRef(Input):
    id: Text
    revision: int = Field(ge=1)


class AdoptPrice(Input):
    device_id: Text
    price: PriceRef


class PriceAdoptOperation(Input):
    action: Literal["price_versions_adopt"]
    adoption_date: date
    items: list[AdoptPrice] = Field(min_length=1)
    fingerprint: Text


class ProjectPricePreview(Input):
    configuration: dict
    adoption_date: date
