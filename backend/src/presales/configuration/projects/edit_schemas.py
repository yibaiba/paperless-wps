from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from presales.configuration.common import Input, Text
from presales.configuration.projects.evolution_schemas import SupplyAllocation
from presales.configuration.projects.schemas import (
    AccessoryAllocation,
    Configuration,
    Deployment,
    Requirement,
    Room,
    System,
)
from presales.quotation.schemas import Quotation, QuotedPrice


class RoomPut(Input):
    action: Literal["room_put"]
    value: Room


class SystemPut(Input):
    action: Literal["system_put"]
    value: System


class RequirementPut(Input):
    action: Literal["requirement_put"]
    value: Requirement


class DeviceInput(Deployment):
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    kind: Literal["hardware", "software", "license", "accessory"]

    @model_validator(mode="after")
    def server_snapshots(self):
        if self.source_snapshot or self.variant_snapshot or self.origin_suggestion:
            raise ValueError("产品快照和配套出处由服务端提供")
        return self


class DevicePut(Input):
    action: Literal["device_put"]
    value: DeviceInput


class Remove(Input):
    action: Literal["remove"]
    collection: Literal["rooms", "systems", "requirements", "devices"]
    id: Text


class SupplySet(Input):
    action: Literal["supply_set"]
    device_id: Text
    allocations: list[SupplyAllocation]


class AccessoryChoice(Input):
    action: Literal["accessory_choice"]
    demand_id: Text
    selected: bool


class AccessoryRemove(Input):
    action: Literal["accessory_remove"]
    allocation_id: Text


class AccessoryApply(Input):
    action: Literal["accessory_apply"]
    fingerprint: Text
    suggestion_id: Text
    variant_id: str | None = None
    source_id: str | None = None
    existing_device_id: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    supply_source: Literal["purchase", "existing", "unknown"] = "unknown"
    supply_evidence: str = ""


class QuoteSet(Input):
    action: Literal["quotation_set"]
    value: Quotation


class PriceSet(Input):
    action: Literal["price_set"]
    value: QuotedPrice


class Reprice(Input):
    action: Literal["price_readopt"]
    device_ids: list[Text]


class DevicePatch(Input):
    action: Literal["device_patch"]
    device_id: Text
    quantity: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    note: str | None = None

    @model_validator(mode="after")
    def fields_present(self):
        if self.quantity is None and self.note is None:
            raise ValueError("请指定数量或备注")
        return self


class PurchaseSet(Input):
    action: Literal["purchase_set"]
    device_id: Text
    quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    evidence: Text


class DescriptionSet(Input):
    action: Literal["description_set"]
    device_id: Text
    text: str | None = None


class SectionSet(Input):
    action: Literal["section_set"]
    device_id: Text
    section: str


class DrawingSet(Input):
    action: Literal["drawing_set"]
    xml: str


class AuthorSet(Input):
    action: Literal["author_set"]
    actor: Text
    evidence: Text


class AccessoryLink(Input):
    action: Literal["accessory_link"]
    value: AccessoryAllocation


class QuotationReplace(Input):
    action: Literal["quotation_replace"]
    value: Quotation | None


class KnowledgeRefresh(Input):
    action: Literal["knowledge_refresh"]
    upgrade: bool = False
    expected_knowledge_snapshot_id: str | None = None
    expected_definition_snapshot_id: str | None = None
    expected_variant_revisions: dict[str, int] = Field(default_factory=dict)
    expected_product_revisions: dict[str, int] = Field(default_factory=dict)


class AccessoryChoiceClear(Input):
    action: Literal["accessory_choice_clear"]
    demand_id: Text


Operation = Annotated[
    AccessoryChoiceClear
    | AccessoryLink
    | QuotationReplace
    | KnowledgeRefresh
    | DrawingSet
    | AuthorSet
    | RoomPut
    | SystemPut
    | RequirementPut
    | DevicePut
    | Remove
    | SupplySet
    | AccessoryChoice
    | AccessoryRemove
    | AccessoryApply
    | QuoteSet
    | PriceSet
    | Reprice
    | DevicePatch
    | SectionSet
    | PurchaseSet
    | DescriptionSet,
    Field(discriminator="action"),
]


class EditPreview(Input):
    configuration: Configuration
    draft_version: int = Field(ge=0)
    expected_revision: int = Field(ge=0)
    operations: list[Operation] = Field(min_length=1)
