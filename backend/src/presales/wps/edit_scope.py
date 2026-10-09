"""Resolve the systems affected by a projected workbook business edit."""

SCOPED_CHANGE_KINDS = {
    "devices",
    "requirements",
    "accessory_allocations",
    "included_allocations",
    "accessory_choices",
    "supply_allocations",
}


def scope_errors(
    option,
    changes,
    *,
    baseline,
    active_system_id,
    active_device_ids=frozenset(),
):
    contexts = (option["checked"], baseline)
    errors = []
    for change in changes:
        if change["kind"] not in SCOPED_CHANGE_KINDS:
            continue
        for label, system_ids in change_targets(
            change,
            contexts=contexts,
            active_system_id=active_system_id,
            active_device_ids=active_device_ids,
        ):
            error = target_scope_error(
                label,
                system_ids=system_ids,
                active_system_id=active_system_id,
            )
            if error and error not in errors:
                errors.append(error)
    return errors


def change_targets(
    change,
    *,
    contexts,
    active_system_id,
    active_device_ids,
):
    kind = change["kind"]
    if kind == "requirements":
        system_ids = {
            value["system_id"]
            for value in (change["before"], change["after"])
            if value and value.get("system_id")
        }
        return [(f"需求 {change['id']}", system_ids)]
    if kind in {"accessory_allocations", "included_allocations"}:
        demand_ids = {
            value["demand_id"]
            for value in (change["before"], change["after"])
            if value and value.get("demand_id")
        }
        return [
            (f"配套需求 {identity}", demand_system_ids(contexts, demand_id=identity))
            for identity in sorted(demand_ids)
        ]
    if kind == "accessory_choices":
        return choice_targets(change, contexts=contexts)
    device_ids = {
        value["device_id"] if kind == "supply_allocations" else value["id"]
        for value in (change["before"], change["after"])
        if value
    }
    return [
        (
            f"产品 {identity}",
            device_system_ids(
                contexts,
                device_id=identity,
                active_system_id=active_system_id,
                active_device_ids=active_device_ids,
            ),
        )
        for identity in sorted(device_ids)
    ]


def choice_targets(change, *, contexts):
    before = {item["demand_id"]: item for item in change["before"] or []}
    after = {item["demand_id"]: item for item in change["after"] or []}
    changed = [
        identity
        for identity in sorted(before.keys() | after.keys())
        if before.get(identity) != after.get(identity)
    ]
    return [
        (f"配套选择 {identity}", demand_system_ids(contexts, demand_id=identity))
        for identity in changed
    ]


def target_scope_error(label, *, system_ids, active_system_id):
    if not system_ids:
        return f"{label} 无法确定所属系统，不能写入当前业务区"
    foreign = system_ids - {active_system_id}
    if not foreign:
        return None
    targets = "、".join(sorted(foreign))
    return f"{label} 属于系统 {targets}，当前业务区为 {active_system_id}；请定位对应业务区后重试"


def device_system_ids(
    contexts,
    *,
    device_id,
    active_system_id,
    active_device_ids,
):
    requirements = requirement_index(contexts)
    system_ids = {
        requirement["system_id"]
        for requirement in requirements.values()
        if requirement.get("device_id") == device_id
        or any(item["device_id"] == device_id for item in requirement.get("allocations", []))
    }
    demand_ids = {
        allocation["demand_id"]
        for context in contexts
        for key in ("accessory_allocations", "included_allocations")
        for allocation in context["configuration"].get(key, [])
        if allocation.get("device_id") == device_id
    }
    for demand_id in demand_ids:
        system_ids.update(demand_system_ids(contexts, demand_id=demand_id))
    if not system_ids and device_id in active_device_ids:
        system_ids.add(active_system_id)
    return system_ids


def demand_system_ids(contexts, *, demand_id):
    requirements = requirement_index(contexts)
    consumer_ids = {
        requirement_id
        for context in contexts
        for suggestion in context.get("suggestions", [])
        if suggestion["id"] == demand_id
        for requirement_id in suggestion.get("consumer_requirement_ids", [])
    }
    return {
        requirements[identity]["system_id"]
        for identity in consumer_ids
        if identity in requirements
    }


def requirement_index(contexts):
    result = {}
    for context in contexts:
        for requirement in context["configuration"].get("requirements", []):
            result.setdefault(requirement["id"], requirement)
    return result
