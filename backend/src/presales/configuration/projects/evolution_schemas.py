from decimal import Decimal
from typing import Literal

from pydantic import Field

from ..common import Authored, Input, Text


class AccessoryChoice(Input):
    demand_id: Text
    selected: bool
    note: str = ""


class SupplyAllocation(Input):
    id: Text
    device_id: Text
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    source: Literal["purchase", "existing", "unknown"]
    evidence: Text


class ConfirmationInput(Authored):
    expected_revision: int = Field(ge=1)
    fingerprint: Text


class RevisionComparison(Input):
    base_revision: int = Field(ge=1)
    target_revision: int = Field(ge=1)
