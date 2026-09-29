from collections import defaultdict
from decimal import Decimal


def allocation_checks(data, *, definitions, engine):
    from ..planning.quantities import role_quantity

    systems = {s["id"]: s for s in data["systems"]}
    packages = {p["id"]: p for p in definitions["packages"]}
    devices = {d["id"]: d for d in data["devices"]}
    counts, checks = defaultdict(list), []
    for requirement in data["requirements"]:
        allocations = requirement.get("allocations", [])
        if not allocations:
            if requirement.get("device_id"):
                counts[requirement["device_id"]].append(
                    (requirement["id"], Decimal(devices[requirement["device_id"]]["quantity"]))
                )
            continue
        for allocation in allocations:
            counts[allocation["device_id"]].append(
                (requirement["id"], Decimal(allocation["quantity"]))
            )
        system = systems[requirement["system_id"]]
        definition = packages.get(system.get("knowledge_package_id"), {}).get("definition", {})
        role = next(
            (r for r in definition.get("roles", []) if r["id"] == requirement.get("role_id")),
            {"id": requirement.get("role_id", "")},
        )
        needed, gap, evidence = role_quantity(role, system, configuration=data, engine=engine)
        allocated = sum((Decimal(a["quantity"]) for a in allocations), Decimal(0))
        checks.append(
            dict(
                kind="role_allocation",
                requirement_id=requirement["id"],
                status="unknown" if gap else "pass" if allocated == needed else "conflict",
                required=str(needed) if needed is not None else None,
                allocated=str(allocated),
                message=gap["message"] if gap else f"需求 {needed}，已分配 {allocated}",
                evidence=[evidence] if evidence else [],
            )
        )
    for identity, uses in counts.items():
        capacity = Decimal(devices[identity]["quantity"])
        if capacity == 1 and all(amount == 1 for _, amount in uses):
            continue  # Single-instance reuse still requires the normal sharing checks.
        if sum((amount for _, amount in uses), Decimal(0)) > capacity:
            checks.append(
                dict(
                    kind="role_allocation",
                    status="conflict",
                    device_id=identity,
                    requirement_ids=[r for r, _ in uses],
                    message="角色分配总量超过设备数量，不能重复抵扣",
                )
            )
    return checks
