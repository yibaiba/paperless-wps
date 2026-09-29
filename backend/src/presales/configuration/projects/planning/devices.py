from copy import deepcopy
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from ..schemas import Deployment
from .questions import question


def stable_id(key):
    return str(uuid5(NAMESPACE_URL, "presales-generated:" + key))


def device_for(context, variant, *, key, quantity, kind, source_id=""):
    sources = variant["source_ids"]
    if source_id and source_id not in sources:
        raise ValueError("指定资料来源不属于候选配置")
    if not sources:
        return None, question(
            "product_source_missing", variant["id"], "source_id", "配置尚未关联已确认来源"
        )
    if not source_id and len(sources) > 1 and variant.get("source_differences"):
        return None, question(
            "product_source_ambiguous",
            variant["id"],
            "source_id",
            "配置的多个来源存在差异，请明确采用来源",
            choices=sources,
        )
    previous = next(
        (
            d
            for d in context.configuration["devices"]
            if (d.get("generated_origin") or {}).get("key") == key
        ),
        None,
    )
    identity = previous["id"] if previous else stable_id(key)
    origin = dict(
        key=key, proposal_id=context.proposal_id, variant_locked=False, quantity_locked=False
    )
    device = Deployment(
        id=identity,
        name=variant["product"]["name"] + " / " + variant["name"],
        variant_id=variant["id"],
        source_id=source_id or sorted(sources)[0],
        quantity=quantity,
        kind=kind,
        generated_origin=origin,
    ).model_dump(mode="json")
    if previous:
        device["note"] = previous["note"]
        old_origin = previous["generated_origin"]
        device["generated_origin"].update(
            variant_locked=old_origin["variant_locked"],
            quantity_locked=old_origin["quantity_locked"],
        )
        if old_origin["quantity_locked"]:
            device["quantity"] = previous["quantity"]
        if previous["variant_id"] == variant["id"] and previous["source_id"] == device["source_id"]:
            device.update(
                variant_snapshot=previous["variant_snapshot"],
                source_snapshot=previous["source_snapshot"],
            )
    return device, None


def put_device(data, device, *, context):
    result = deepcopy(data)
    result["devices"] = [d for d in result["devices"] if d["id"] != device["id"]] + [device]
    previous = next((d for d in context.configuration["devices"] if d["id"] == device["id"]), None)
    allocations = [a for a in result["supply_allocations"] if a["device_id"] == device["id"]]
    if not previous or context.configuration["generation"]["supply_source"] == "purchase":
        # A customer-owned allocation is never converted to a new purchase by generation.
        if not any(a["source"] == "existing" for a in allocations):
            state = result["generation"]
            result["supply_allocations"] = [
                a for a in result["supply_allocations"] if a["device_id"] != device["id"]
            ]
            result["supply_allocations"].append(
                dict(
                    id=stable_id("supply:" + device["id"]),
                    device_id=device["id"],
                    quantity=device["quantity"],
                    source=state["supply_source"],
                    evidence=state["supply_evidence"] or "供货来源尚待客户确认",
                )
            )
    return result


def bind_role(data, requirement_id, device_id):
    return dict(
        data,
        requirements=[
            dict(r, device_id=device_id) if r["id"] == requirement_id else r
            for r in data["requirements"]
        ],
    )


def allocation(data, demand, device_id, *, quantity):
    item = dict(
        id=stable_id("allocation:" + demand["id"] + ":" + device_id),
        demand_id=demand["id"],
        device_id=device_id,
        quantity=str(quantity),
        evidence="根据已确认配套依据生成，采用时整批确认",
    )
    return dict(
        data,
        accessory_allocations=[a for a in data["accessory_allocations"] if a["id"] != item["id"]]
        + [item],
    )


def available(data, device, demand, demands):
    if demand["rule"]["allocation_mode"] == "shareable":
        return Decimal(device["quantity"])
    rules = {s["id"]: s["rule"] for s in demands}
    used = sum(
        (
            Decimal(a["quantity"])
            for a in data["accessory_allocations"]
            if a["device_id"] == device["id"]
            and rules.get(a["demand_id"], {}).get("allocation_mode", "consumable") == "consumable"
        ),
        Decimal(0),
    )
    return max(Decimal(device["quantity"]) - used, Decimal(0))
