"""Clone deployment facts, never its uses, fulfillment or adopted commercial decisions."""

from presales.quotation.schemas import QuotedPrice

from ..drawing import project_drawing


def clone_device(data, operation):
    original = next((d for d in data["devices"] if d["id"] == operation.source_device_id), None)
    if original is None:
        raise ValueError("原设备不存在，无法复制")
    if any(d["id"] == operation.new_device_id for d in data["devices"]):
        raise ValueError("新设备标识已存在，不能覆盖已有设备")
    if any(a.device_id != operation.new_device_id for a in operation.supply_allocations):
        raise ValueError("复制设备的供货分配必须属于新设备")
    cloned = dict(
        original,
        id=operation.new_device_id,
        name=original["name"] + " 副本",
        origin_suggestion=None,
        generated_origin=None,
    )
    result = dict(
        data,
        devices=[*data["devices"], cloned],
        supply_allocations=[
            *data["supply_allocations"],
            *[a.model_dump(mode="json") for a in operation.supply_allocations],
        ],
    )
    if data.get("quotation"):
        pending = QuotedPrice(
            device_id=cloned["id"],
            variant_id=cloned["variant_id"],
            source_id=cloned["source_id"],
            mode="pending",
            evidence="复制的新设备尚未采用报价价格，请独立确认",
        ).model_dump(mode="json")
        result["quotation"] = dict(
            data["quotation"], prices=[*data["quotation"]["prices"], pending]
        )
    result["drawing_xml"] = project_drawing(
        data["drawing_xml"], devices=result["devices"], add_ids=[cloned["id"]]
    )
    return result
