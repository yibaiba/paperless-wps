"""Report concrete dependency paths without trusting text labels as graph edges."""


def dependency_cycle(data, demand, target_id, demands):
    if not target_id:
        return None
    variants = {d["id"]: d["variant_id"] for d in data["devices"]}
    by_id = {d["id"]: d for d in demands}
    parents = {}
    for a in data["accessory_allocations"]:
        d = by_id.get(a["demand_id"])
        if d:
            parents.setdefault(a["device_id"], []).extend(
                i["device_id"] for i in d.get("quantity_inputs", [])
            )

    return find_cycle(
        variants, parents, target_id=target_id, owners=demand.get("quantity_inputs", [])
    )


def find_cycle(variants, parents, *, target_id, owners):
    def visit(identity, seen):
        if identity in seen:
            return None
        if variants[identity] == variants[target_id]:
            return [variants[target_id], *[variants[i] for i in reversed(seen)], variants[identity]]
        for parent in parents.get(identity, []):
            found = visit(parent, [*seen, identity])
            if found:
                return found
        return None

    for owner in owners:
        found = visit(owner["device_id"], [])
        if found:
            return found
    return None
