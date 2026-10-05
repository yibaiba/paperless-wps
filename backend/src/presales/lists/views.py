from presales.configuration.projects.calculation.usage.versioning import current_projection
from presales.rules.calculation import digest

from .queries import page


def summary(record):
    data = record["configuration"]
    checked = record.get("checked") or record
    quote = checked.get("quotation_output")
    return dict(
        id=record.get("id"),
        revision=record.get("revision"),
        name=record.get("name"),
        project_id=record.get("project_id"),
        base_revision=record.get("base_revision"),
        rooms=data["rooms"],
        systems=data["systems"],
        device_count=len(data["devices"]),
        requirement_count=len(data["requirements"]),
        check_fingerprint=record.get("check_fingerprint"),
        calculation_fingerprint=checked.get("fingerprint"),
        usage_projection=checked.get("usage_projection"),
        check_current=current_projection(checked)
        and (
            record.get("checked_config_hash") == digest(data)
            if "checked" in record
            else bool(record.get("fingerprint"))
        ),
        quotation_total=quote.get("total") if quote else None,
        known_subtotal=quote.get("known_subtotal") if quote else None,
        knowledge_snapshot_id=data.get("knowledge_snapshot_id"),
        definition_snapshot_id=data.get("definition_snapshot_id"),
        calculation_version=data["calculation_version"],
        catalog_snapshot_id=record.get("catalog_snapshot_id"),
    )


def read_view(record, request):
    result = summary(record)
    if request.view == "summary":
        return result
    checked = record.get("checked") or record
    if request.view == "device_usages":
        items = checked.get("device_usages", [])
        if request.device_id:
            items = [u for u in items if u["device_id"] == request.device_id]
        return dict(result, **page(items, request))
    if request.view == "quotation":
        output = checked.get("quotation_output") or {}
        pagination = page(output.get("lines", []), request)
        pagination["total_items"] = pagination.pop("total")
        return dict(
            result,
            metadata={
                k: v
                for k, v in (record["configuration"].get("quotation") or {}).items()
                if k != "prices"
            },
            total=output.get("total"),
            known_subtotal=output.get("known_subtotal"),
            **pagination,
        )
    if request.view == "requirements":
        return dict(result, **page(record["configuration"]["requirements"], request))
    if request.view == "allocations":
        items = [
            dict(a, allocation_type=kind)
            for kind in ("supply", "accessory", "included")
            for a in record["configuration"].get(kind + "_allocations", [])
        ]
        return dict(result, **page(items, request))
    if request.view == "issues":
        items = checked.get("checks", []) + (checked.get("quotation_output") or {}).get(
            "issues", []
        )
        items += [dict(kind="accessory", **s) for s in checked.get("suggestions", [])]
        return dict(result, **page(items, request))
    if request.view == "evidence":
        return dict(
            result, **page(record["configuration"].get("knowledge_snapshot") or [], request)
        )
    if request.view == "changes":
        usages = [
            dict(kind="device_usage", id=c["device_id"], before=c["previous"], after=c["current"])
            for c in record.get("usage_changes", [])
        ]
        return dict(result, **page([*record.get("changes", []), *usages], request))
    key = "procurement_lines" if request.view == "procurement" else "lines"
    devices = {d["id"]: d for d in record["configuration"]["devices"]}
    items = [
        dict(
            line,
            variant_id=devices[line["device_id"]]["variant_id"],
            source_id=devices[line["device_id"]]["source_id"],
        )
        for line in checked.get("project_output", {}).get(key, [])
    ]
    return dict(result, **page(items, request))
