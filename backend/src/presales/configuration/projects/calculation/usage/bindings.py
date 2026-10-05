"""Resolve all confirmed role/need links by stable identities, without last-match wins."""

from collections import defaultdict


def fulfilled_links(data, *, definitions, demands):
    packages = {p["id"]: p for p in definitions["packages"]}
    catalog = {d["id"]: d for d in definitions["definitions"]}
    systems = {s["id"]: s for s in data["systems"]}
    parents = defaultdict(list)
    for requirement in data["requirements"]:
        parents[requirement["system_id"], requirement.get("role_id", "")].append(requirement)
    assignments = defaultdict(set)
    for allocation in data.get("accessory_allocations", []):
        assignments[allocation["device_id"]].add(allocation["demand_id"])
    result = {}
    for requirement in data["requirements"]:
        system = systems[requirement["system_id"]]
        package = packages.get(system.get("knowledge_package_id"))
        definition = (
            package["definition"] if package else catalog.get(system.get("definition_id"), {})
        )
        role = next(
            (r for r in definition.get("roles", []) if r["id"] == requirement.get("role_id")), {}
        )
        binding = role.get("fulfilled_by")
        if not binding or binding["status"] != "confirmed" or not requirement.get("device_id"):
            continue
        links = matching_links(
            parents[system["id"], binding["role_id"]],
            demands=demands,
            need_key=binding["need_key"],
            assigned=assignments[requirement["device_id"]],
        )
        if links:
            result[requirement["id"]] = links
    return result


def matching_links(parents, *, demands, need_key, assigned):
    return sorted(
        [
            dict(requirement_id=p.get("allocation_parent_id", p["id"]), demand_id=d["id"])
            for p in parents
            for d in demands
            if d["id"] in assigned
            and d["need_key"] == need_key
            and d["status"] == "pass"
            and p["id"] in d["consumer_requirement_ids"]
        ],
        key=lambda link: (link["requirement_id"], link["demand_id"]),
    )


def role_need_ids(data, *, system_id, role_id, need_key, demands):
    parents = [
        r
        for r in data["requirements"]
        if r["system_id"] == system_id and r.get("role_id") == role_id
    ]
    return {
        d["id"]
        for d in demands
        if d["need_key"] == need_key
        and any(p["id"] in d["consumer_requirement_ids"] for p in parents)
    }
