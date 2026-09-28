from collections import defaultdict
from decimal import Decimal


def supply_projection(data):
    by_device = defaultdict(list)
    for allocation in data.get("supply_allocations", []):
        by_device[allocation["device_id"]].append(allocation)
    checks, summaries = [], {}
    for device in data["devices"]:
        items = by_device[device["id"]]
        totals = {
            key: sum((Decimal(a["quantity"]) for a in items if a["source"] == key), Decimal(0))
            for key in ("purchase", "existing", "unknown")
        }
        required = Decimal(device["quantity"])
        allocated = sum(totals.values(), Decimal(0))
        missing = max(required - allocated, Decimal(0))
        status = (
            "conflict"
            if allocated > required
            else ("unknown" if missing or totals["unknown"] else "pass")
        )
        summary = dict(
            device_id=device["id"],
            required=str(required),
            **{k: str(v) for k, v in totals.items()},
            unassigned=str(missing),
        )
        summaries[device["id"]] = summary
        checks.append(
            dict(
                kind="supply",
                status=status,
                **summary,
                message=(
                    "供货分配超过部署数量"
                    if status == "conflict"
                    else "供货来源或数量待确认"
                    if status == "unknown"
                    else "供货数量已核对"
                ),
            )
        )
    return summaries, checks
