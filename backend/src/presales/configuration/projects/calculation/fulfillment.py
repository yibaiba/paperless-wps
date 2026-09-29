"""Collapse a reviewed role/need alias, without treating it as cross-system sharing."""


def fulfillment_aliases(data, *, definitions, demands):
    packages = {p["id"]: p for p in definitions["packages"]}
    requirements = data["requirements"]
    result = {}
    for system in data["systems"]:
        package = packages.get(system.get("knowledge_package_id"), {})
        roles = {r["id"]: r for r in package.get("definition", {}).get("roles", [])}
        for requirement in [r for r in requirements if r["system_id"] == system["id"]]:
            binding = roles.get(requirement.get("role_id"), {}).get("fulfilled_by")
            if not binding or binding["status"] != "confirmed" or not requirement["device_id"]:
                continue
            parents = [
                r
                for r in requirements
                if r["system_id"] == system["id"] and r["role_id"] == binding["role_id"]
            ]
            for parent in parents:
                matches = {
                    d["id"]
                    for d in demands
                    if d["need_key"] == binding["need_key"]
                    and parent["id"] in d["consumer_requirement_ids"]
                    and d["status"] == "pass"
                }
                if any(
                    a["demand_id"] in matches and a["device_id"] == requirement["device_id"]
                    for a in data["accessory_allocations"]
                ):
                    result[requirement["id"]] = parent.get("allocation_parent_id", parent["id"])
    return result


def alias_consumers(usages, aliases):
    for usage in usages:
        for consumer in usage["consumers"]:
            if consumer["requirement_id"] in aliases:
                consumer["fulfilled_by_requirement_id"] = aliases[consumer["requirement_id"]]
    return usages
