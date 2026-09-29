from decimal import Decimal

from ..schemas import Configuration


def edit_inclusion(data, operation, *, repository):
    allocations = data.get("included_allocations", [])
    if operation.action == "included_remove":
        if not any(a["id"] == operation.allocation_id for a in allocations):
            raise ValueError("已含抵扣不存在")
        return dict(
            data,
            included_allocations=[a for a in allocations if a["id"] != operation.allocation_id],
        )
    value = operation.value.model_dump(mode="json")
    current = next((a for a in allocations if a["id"] == value["id"]), None)
    if current:
        if current != value:
            raise ValueError("修改已含抵扣请先移除原关联")
        return data
    checked = repository.check(Configuration.model_validate(data))
    demand = next((s for s in checked["suggestions"] if s["id"] == value["demand_id"]), None)
    if not demand or not demand.get("selected") or demand["status"] != "pass":
        raise ValueError("请先选择并核对配套需求")
    offer = next(
        (
            o
            for o in demand.get("included_offers", [])
            if all(o[k] == value[k] for k in ("device_id", "included_item_id"))
        ),
        None,
    )
    if not offer or offer["status"] != "pass":
        raise ValueError(offer["reason"] if offer else "没有匹配且已确认的包含依据")
    if any(offer[k] != value[k] for k in ("host_variant_id", "host_variant_revision")):
        raise ValueError("宿主配置修订已变化，请重新检查")
    quantity = Decimal(value["quantity"])
    if quantity > Decimal(offer["available"]) or quantity > Decimal(demand["missing"]):
        raise ValueError("抵扣数量超过未占用的已含数量或当前缺量")
    return dict(checked["configuration"], included_allocations=[*allocations, value])
