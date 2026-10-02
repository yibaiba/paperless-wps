from collections import defaultdict
from decimal import Decimal


def allocation_checks(data, *, definitions, engine, fulfilled_ids=frozenset()):
    systems = {s["id"]: s for s in data["systems"]}
    packages = {p["id"]: p for p in definitions["packages"]}
    catalog = {d["id"]: d for d in definitions["definitions"]}
    devices = {d["id"]: d for d in data["devices"]}
    counts, checks = defaultdict(list), []
    for requirement in data["requirements"]:
        allocations = role_allocations(requirement, devices)
        if not allocations:
            continue
        # Confirmed aliases refer to accessory allocations, not additional stock use.
        if requirement["id"] in fulfilled_ids:
            checks.extend(
                device_allocation_checks(
                    {
                        a["device_id"]: [(requirement["id"], Decimal(a["quantity"]))]
                        for a in allocations
                    },
                    devices,
                )
            )
            continue
        for allocation in allocations:
            counts[allocation["device_id"]].append(
                (requirement["id"], Decimal(allocation["quantity"]))
            )
        system = systems[requirement["system_id"]]
        package = packages.get(system.get("knowledge_package_id"))
        definition = (
            package["definition"] if package else catalog.get(system.get("definition_id"), {})
        )
        role = next(
            (r for r in definition.get("roles", []) if r["id"] == requirement.get("role_id")),
            {"id": requirement.get("role_id", "")},
        )
        checks.append(
            quantity_check(
                requirement,
                allocations=allocations,
                role=role,
                system=system,
                data=data,
                engine=engine,
            )
        )
    return checks + device_allocation_checks(counts, devices)


def role_allocations(requirement, devices):
    if requirement.get("allocations"):
        return requirement["allocations"]
    device = devices.get(requirement.get("device_id"))
    return [dict(device_id=device["id"], quantity=device["quantity"])] if device else []


def quantity_check(requirement, *, allocations, role, system, data, engine):
    from ..planning.quantities import role_quantity

    needed, gap, evidence = role_quantity(role, system, configuration=data, engine=engine)
    allocated = sum((Decimal(a["quantity"]) for a in allocations), Decimal(0))
    return dict(
        kind="role_allocation",
        requirement_id=requirement["id"],
        system_id=system["id"],
        role_id=role["id"],
        status="unknown" if gap else "pass" if allocated == needed else "conflict",
        required=str(needed) if needed is not None else None,
        allocated=str(allocated),
        message=gap["message"] if gap else f"需求 {needed}，已分配 {allocated}",
        evidence=[evidence] if evidence else [],
        quantity_gap=gap,
    )


def device_allocation_checks(counts, devices):
    checks = []
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
