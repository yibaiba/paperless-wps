from decimal import Decimal

from ..schemas import Configuration, SuggestionApply
from .manual_edits import mark


def link_accessory(data, value, *, repository):
    current = next((a for a in data["accessory_allocations"] if a["id"] == value.id), None)
    if current and current != value.model_dump(mode="json"):
        raise ValueError("修改配套分配请先移除原关联，再重新分配")
    if current:
        return data
    checked = repository.check(Configuration.model_validate(data))
    demand = next((s for s in checked["suggestions"] if s["id"] == value.demand_id), None)
    if demand is None:
        raise ValueError("配套需求已变化，请重新检查后关联")
    result = repository.apply(
        SuggestionApply(
            configuration=checked["configuration"],
            fingerprint=checked["fingerprint"],
            suggestion_id=value.demand_id,
            existing_device_id=value.device_id,
            quantity=value.quantity,
        )
    )["configuration"]
    before = {a["id"] for a in data["accessory_allocations"]}
    added = [a for a in result["accessory_allocations"] if a["id"] not in before]
    if len(added) != 1 or Decimal(added[0]["quantity"]) != value.quantity:
        raise ValueError("配套分配结果与请求数量不一致，请重新检查")
    result["accessory_allocations"] = [
        value.model_dump(mode="json") if a["id"] == added[0]["id"] else a
        for a in result["accessory_allocations"]
    ]
    return mark(result, "accessory_allocations", value.id)
