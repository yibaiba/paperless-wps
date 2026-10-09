from datetime import date
from typing import Literal

from pydantic import Field

from presales.application.contracts import Input, Text


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
