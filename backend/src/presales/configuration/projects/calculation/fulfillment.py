"""Collapse a reviewed role/need alias, without treating it as cross-system sharing."""


def fulfillment_aliases(data, *, definitions, demands):
    packages = {p["id"]: p for p in definitions["packages"]}
    catalog = {d["id"]: d for d in definitions["definitions"]}
    requirements = data["requirements"]
    result = {}
    for system in data["systems"]:
        package = packages.get(system.get("knowledge_package_id"))
        definition = (
            package["definition"] if package else catalog.get(system.get("definition_id"), {})
        )
        roles = {r["id"]: r for r in definition.get("roles", [])}
        for requirement in [r for r in requirements if r["system_id"] == system["id"]]:
            binding = roles.get(requirement.get("role_id"), {}).get("fulfilled_by")
            if not binding or binding["status"] != "confirmed" or not requirement["device_id"]:
                continue
            link = fulfillment_link(requirement, binding=binding, data=data, demands=demands)
            if link:
                result[requirement["id"]] = link
    return result


def fulfillment_link(requirement, *, binding, data, demands):
    parents = [
        r
        for r in data["requirements"]
        if r["system_id"] == requirement["system_id"] and r["role_id"] == binding["role_id"]
    ]
    result = None
    for parent in parents:
        matches = {
            d["id"]
            for d in demands
            if d["need_key"] == binding["need_key"]
            and parent["id"] in d["consumer_requirement_ids"]
            and d["status"] == "pass"
        }
        linked = list(
            dict.fromkeys(
                a["demand_id"]
                for a in data["accessory_allocations"]
                if a["demand_id"] in matches and a["device_id"] == requirement["device_id"]
            )
        )
        if linked:
            result = dict(
                requirement_id=parent.get("allocation_parent_id", parent["id"]),
                demand_ids=linked,
            )
    return result


def fulfilled_requirement_ids(data, *, aliases, fulfilled):
    linked, unlinked = set(), set()
    for requirement in data["requirements"]:
        identity = requirement["id"]
        target = linked if identity in fulfilled else unlinked
        target.add(aliases.get(identity, identity))
    return linked - unlinked


def alias_consumers(usages, aliases):
    return [
        dict(usage, consumers=[alias_consumer(c, aliases) for c in usage["consumers"]])
        for usage in usages
    ]


def alias_consumer(consumer, aliases):
    link = aliases.get(consumer["requirement_id"])
    if not link or consumer["via"] != "direct":
        return consumer
    return dict(
        consumer,
        fulfilled_by_requirement_id=link["requirement_id"],
        fulfilled_by_demand_ids=link["demand_ids"],
    )
