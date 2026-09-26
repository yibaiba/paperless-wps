def project_output(data, device_usages, readiness):
    usage_by_device = {item["device_id"]: item for item in device_usages}
    return {
        "status": "confirmed" if readiness["ready_for_confirmed_output"] else "draft",
        "ready_for_confirmed_output": readiness["ready_for_confirmed_output"],
        "knowledge_snapshot_id": data.get("knowledge_snapshot_id"),
        "calculation_version": data.get("calculation_version", 1),
        "lines": [
            output_line(device, usage_by_device.get(device["id"]))
            for device in data.get("devices", [])
        ],
    }


def output_line(device, usage):
    source = device.get("source_snapshot") or {}
    variant = device.get("variant_snapshot") or {}
    product = variant.get("product") or {}
    consumers = (usage or {}).get("consumers", [])
    return {
        "device_id": device["id"],
        "kind": device["kind"],
        "name": device["name"],
        "model": source.get("model") or product.get("model") or "",
        "specification": source.get("specification") or "",
        "unit": source.get("unit") or "",
        "quantity": device["quantity"],
        "note": device.get("note", ""),
        "prices": source.get("prices") or {},
        "consumers": [
            {
                "requirement_id": item["requirement_id"],
                "system_name": item["system_name"],
                "role": item["role"],
                "via": item["via"],
            }
            for item in consumers
        ],
        "source": {
            "id": source.get("id") or device.get("source_id"),
            "import_id": source.get("import_id"),
            "sheet": source.get("sheet"),
            "row": source.get("row"),
        },
    }
