from typing import Annotated, Literal

from pydantic import Field, field_validator

from ..schemas import Device, Input, Relation, SystemGroup, Text


class AddProduct(Input):
    action: Literal["add_product"]
    product_id: Text
    shape: Literal["device", "terminal", "switch", "rack"] = "device"
    bind_id: str | None = None


class AddProducts(Input):
    action: Literal["add_products"]
    product_ids: list[Text] = Field(min_length=1)
    shape: Literal["device", "terminal", "switch", "rack"] = "device"

    @field_validator("product_ids")
    @classmethod
    def unique_products(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("所选产品不能重复；设备数量可在产品面板调整")
        return values


class EditDevice(Input):
    action: Literal["device"]
    device: Device


class EditGroup(Input):
    action: Literal["group"]
    group: SystemGroup


class EditRelation(Input):
    action: Literal["relation"]
    relation: Relation


class Remove(Input):
    action: Literal["remove"]
    id: Text


Operation = Annotated[
    AddProduct | AddProducts | EditDevice | EditGroup | EditRelation | Remove,
    Field(discriminator="action"),
]


class DrawingInput(Input):
    xml: Text
    operation: Operation | None = None
