from uuid import uuid4


def edit_quote_device(data, operation):
    """Update the private working copy owned by edit_configuration, never persisted input."""
    device = next((d for d in data["devices"] if d["id"] == operation.device_id), None)
    if device is None:
        raise ValueError("设备不存在，当前修改未应用")
    if data.get("quotation") is None:
        raise ValueError("请先填写报价信息")
    if operation.action == "description_set":
        descriptions = data["quotation"].setdefault("descriptions", {})
        if operation.text is None:
            descriptions.pop(device["id"], None)
        else:
            descriptions[device["id"]] = dict(
                variant_id=device["variant_id"], source_id=device["source_id"], text=operation.text
            )
        return data
    # Purchase editing never infers deployment or consumes customer-owned/unknown stock.
    previous = data.get("supply_allocations", [])
    purchased = [
        a for a in previous if a["device_id"] == device["id"] and a["source"] == "purchase"
    ]
    data["supply_allocations"] = [
        a for a in previous if a["device_id"] != device["id"] or a["source"] != "purchase"
    ]
    if operation.quantity:
        data["supply_allocations"].append(
            dict(
                id=purchased[0]["id"] if purchased else str(uuid4()),
                device_id=device["id"],
                quantity=str(operation.quantity),
                source="purchase",
                evidence=operation.evidence,
            )
        )
    return data
