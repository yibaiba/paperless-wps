from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from presales.configuration.common import Input, Text

TEMPLATE_ID = "meeting-system-v1"
TAX_TERMS = (
    "含13%增值税发票和运费（运费指物流将货物运送至指定收货地址的费用，"
    "不含国外运费、二次转运费和搬运费）"
)


class QuotedPrice(Input):
    device_id: Text
    variant_id: Text
    source_id: Text
    mode: Literal["source", "manual", "import"] = "source"
    price_column: str = ""
    unit_price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    evidence: str = ""

    @model_validator(mode="after")
    def manual_evidence(self):
        if self.mode == "manual" and (self.unit_price is None or not self.evidence):
            raise ValueError("人工单价必须提供金额及采用依据")
        if self.mode == "import" and not self.evidence.strip():
            raise ValueError("导入价格必须保留文件或粘贴来源依据")
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
