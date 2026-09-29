from decimal import Decimal

from pydantic import Field

from ..common import Input, Text


class IncludedAllocation(Input):
    id: Text
    demand_id: Text
    device_id: Text
    included_item_id: Text
    host_variant_id: Text
    host_variant_revision: int = Field(ge=1)
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    evidence: Text
