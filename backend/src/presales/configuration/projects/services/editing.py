from copy import deepcopy

from presales.configuration.projects.drawing import project_drawing
from presales.configuration.projects.schemas import Configuration, SuggestionApply
from presales.quotation.schemas import Quotation

from .device_removal import remove_devices
from .manual_edits import mark, prune
from .quotation_editing import edit_quote_device

PUT_COLLECTIONS = {
    "room_put": "rooms",
    "system_put": "systems",
    "requirement_put": "requirements",
    "device_put": "devices",
}


class EditError(ValueError):
    def __init__(self, index, operation, message):
        self.detail = dict(
            operation_index=index,
            device_id=getattr(operation, "device_id", None),
            action=operation.action,
            message=message,
        )
        super().__init__(f"第 {index + 1} 项修改：{message}")


def edit_configuration(configuration, operations, *, repository):
    data = deepcopy(configuration)
    for index, operation in enumerate(operations):
        try:
            data = apply_operation(data, operation=operation, repository=repository)
        except ValueError as error:
            raise EditError(index, operation, str(error)) from error
    return Configuration.model_validate(prune(data))


def replace_item(items, value, *, key="id"):
    if any(item[key] == value[key] for item in items):
        return [value if item[key] == value[key] else item for item in items]
    return [*items, value]


def apply_operation(data, *, operation, repository):
    action = operation.action
    if action == "requirements_patch":
        from ..planning.requirements import patch_requirements

        return patch_requirements(data, operation, repository=repository)
    if action == "proposal_apply":
        from ..planning.application import apply_proposal

        return apply_proposal(data, operation, repository=repository)
    if action == "price_versions_adopt":
        from presales.catalog_updates.project_prices import adopt_versions

        return adopt_versions(repository.session, data, operation)
    if action == "system_setup":
        from .setup import apply_setup

        return apply_setup(data, operation, session=repository.session)
    if action in {"included_link", "included_remove"}:
        from .inclusions import edit_inclusion

        return edit_inclusion(data, operation, repository=repository)
    if action == "accessory_choice_clear":
        data["accessory_choices"] = [
            c for c in data["accessory_choices"] if c["demand_id"] != operation.demand_id
        ]
        return data
    if action == "quotation_replace":
        data["quotation"] = operation.value.model_dump(mode="json") if operation.value else None
        return data
    if action == "knowledge_refresh":
        from .refreshing import refresh_knowledge

        return refresh_knowledge(data, operation, repository=repository)
    if action == "accessory_link":
        from .linking import link_accessory

        return link_accessory(data, operation.value, repository=repository)
    if action == "drawing_set":
        data["drawing_xml"] = project_drawing(operation.xml, devices=data["devices"])
        return data
    if action == "author_set":
        data.update(actor=operation.actor, evidence=operation.evidence)
        return data
    if action in ("purchase_set", "description_set"):
        return edit_quote_device(data, operation)
    if action in ("device_patch", "section_set"):
        return patch_device(data, operation)
    if action in PUT_COLLECTIONS:
        return put(data, operation)
    if action == "remove":
        return remove(data, operation, repository=repository)
    if action == "supply_set":
        if any(a.device_id != operation.device_id for a in operation.allocations):
            raise ValueError("供货分配必须属于指定设备")
        data["supply_allocations"] = [
            a for a in data["supply_allocations"] if a["device_id"] != operation.device_id
        ] + [a.model_dump(mode="json") for a in operation.allocations]
    elif action == "accessory_choice":
        value = dict(
            demand_id=operation.demand_id, selected=operation.selected, note="Agent 明确选择"
        )
        data["accessory_choices"] = replace_item(data["accessory_choices"], value, key="demand_id")
    elif action == "accessory_remove":
        if not any(a["id"] == operation.allocation_id for a in data["accessory_allocations"]):
            raise ValueError("配套分配不存在")
        data["accessory_allocations"] = [
            a for a in data["accessory_allocations"] if a["id"] != operation.allocation_id
        ]
    elif action == "accessory_apply":
        request = operation.model_dump(mode="json", exclude={"action"})
        before = {d["id"] for d in data["devices"]}
        data = repository.apply(SuggestionApply(configuration=data, **request))["configuration"]
        added = [d["id"] for d in data["devices"] if d["id"] not in before]
        data["drawing_xml"] = project_drawing(
            data["drawing_xml"], devices=data["devices"], add_ids=added
        )
    else:
        quote_edit(data, operation)
    return data


def put(data, operation):
    collection = PUT_COLLECTIONS[operation.action]
    value = operation.value.model_dump(mode="json")
    previous = next((i for i in data[collection] if i["id"] == value["id"]), None)
    if collection == "requirements" and any(
        (previous or {}).get(k) != value.get(k) for k in ("device_id", "allocations")
    ):
        data = mark(
            data, collection, value["id"], enabled=bool(value["device_id"] or value["allocations"])
        )
    if collection == "devices" and previous:
        if previous.get("generated_origin"):
            value["generated_origin"] = dict(
                previous["generated_origin"],
                variant_locked=previous["generated_origin"]["variant_locked"]
                or previous["variant_id"] != value["variant_id"],
                quantity_locked=previous["generated_origin"]["quantity_locked"]
                or previous["quantity"] != value["quantity"],
            )
        if all(previous[k] == value[k] for k in ("variant_id", "source_id")):
            for key in ("variant_snapshot", "source_snapshot", "origin_suggestion"):
                value[key] = previous.get(key)
    data[collection] = replace_item(data[collection], value)
    if collection == "devices":
        data["drawing_xml"] = project_drawing(
            data["drawing_xml"], devices=data["devices"], add_ids=[] if previous else [value["id"]]
        )
    return data


def remove(data, operation, *, repository):
    from ..planning.references import remove_generation_references

    collection, identity = operation.collection, operation.id
    removed_ids = {identity} | {
        r["id"]
        for r in data["requirements"]
        if collection == "systems" and r["system_id"] == identity
    }
    if not any(i["id"] == identity for i in data[collection]):
        raise ValueError("待删除对象不存在")
    if collection == "devices":
        checked = repository.check(Configuration.model_validate(data))
        return remove_devices(data, {identity}, demands=checked["suggestions"])
    data[collection] = [i for i in data[collection] if i["id"] != identity]
    if collection == "rooms":
        data["systems"] = [
            dict(s, room_id=None) if s["room_id"] == identity else s for s in data["systems"]
        ]
    if collection == "systems":
        data["requirements"] = [r for r in data["requirements"] if r["system_id"] != identity]
    data["generation"] = remove_generation_references(data["generation"], removed_ids)
    return data


def quote_edit(data, operation):
    if operation.action == "quotation_set":
        merged = {
            **(data.get("quotation") or {}),
            **operation.value.model_dump(mode="json", exclude_unset=True),
        }
        if data.get("quotation") is None and not merged.get("price_adoption_date"):
            from presales.catalog_updates.prices import beijing_today

            merged["price_adoption_date"] = str(beijing_today())
        data["quotation"] = Quotation.model_validate(merged).model_dump(mode="json")
        return
    quote = data.get("quotation")
    if quote is None:
        raise ValueError("请先填写报价信息")
    if operation.action == "price_set":
        value = operation.value.model_dump(mode="json")
        if not any(d["id"] == value["device_id"] for d in data["devices"]):
            raise ValueError("报价引用的设备不存在")
        quote["prices"] = replace_item(quote["prices"], value, key="device_id")
    elif operation.action == "price_readopt":
        quote["prices"] = [p for p in quote["prices"] if p["device_id"] not in operation.device_ids]
    else:
        raise ValueError("不支持的业务操作")


def patch_device(data, operation):
    device = next((d for d in data["devices"] if d["id"] == operation.device_id), None)
    if device is None:
        raise ValueError("设备不存在，当前修改未应用")
    if operation.action == "section_set":
        if data.get("quotation") is None:
            raise ValueError("请先填写报价信息")
        data["quotation"]["sections"][operation.device_id] = operation.section
        return data
    changes = operation.model_dump(mode="json", exclude={"action", "device_id"}, exclude_none=True)
    if operation.quantity is not None and device.get("generated_origin"):
        changes["generated_origin"] = dict(device["generated_origin"], quantity_locked=True)
    data["devices"] = [
        dict(d, **changes) if d["id"] == device["id"] else d for d in data["devices"]
    ]
    if operation.quantity is not None:
        data["drawing_xml"] = project_drawing(
            data["drawing_xml"], devices=data["devices"], add_ids=[]
        )
    return data
