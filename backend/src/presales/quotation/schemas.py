from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from presales.application.contracts import Input, Text

TEMPLATE_ID = "meeting-system-v1"
TAX_TERMS = (
    "含13%增值税发票和运费（运费指物流将货物运送至指定收货地址的费用，"
    "不含国外运费、二次转运费和搬运费）"
)


class PriceReference(Input):
    id: Text
    revision: int = Field(ge=1)
    adopted_on: date
    configuration_hash: Text


class QuotedPrice(Input):
    device_id: Text
    variant_id: Text
    source_id: Text
    mode: Literal["source", "manual", "import", "version", "pending"] = "source"
    price_column: str = ""
    unit_price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    evidence: str = ""
    price_reference: PriceReference | None = None

    @model_validator(mode="after")
    def manual_evidence(self):
        if self.mode == "pending" and (self.unit_price is not None or not self.evidence):
            raise ValueError("待确认价格须保留原因且不得填写金额")
        if self.mode == "manual" and (self.unit_price is None or not self.evidence):
            raise ValueError("人工单价必须提供金额及采用依据")
        if self.mode == "import" and not self.evidence.strip():
            raise ValueError("导入价格必须保留文件或粘贴来源依据")
        if self.mode == "version" and (not self.price_reference or self.unit_price is None):
            raise ValueError("版本价格必须携带固定金额与修订引用")
        return self


class QuotedDescription(Input):
    variant_id: Text
    source_id: Text
    text: str


class Quotation(Input):
    template_id: Literal["meeting-system-v1"] = TEMPLATE_ID
    currency: Literal["CNY"] = "CNY"
    customer: str = ""
    project_name: str = ""
    sales_contact: str = ""
    designer_contact: str = ""
    design_date: date | None = None
    price_adoption_date: date | None = None
    room_description: str = ""
    price_column: str = ""
    tax_terms: Literal[TAX_TERMS] = TAX_TERMS
    prices: list[QuotedPrice] = Field(default_factory=list)
    sections: dict[str, str] = Field(default_factory=dict)
    descriptions: dict[str, QuotedDescription] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_prices(self):
        ids = [p.device_id for p in self.prices]
        if len(ids) != len(set(ids)):
            raise ValueError("同一设备不能重复指定报价单价")
        return self
