"""Resolve selection requirements only from roles fulfilled by this accessory need."""

from .questions import question


def accessory_selection(context, *, tasks, demand):
    consumers = [t for t in tasks if t["requirement"]["id"] in demand["consumer_requirement_ids"]]
    parents = {(t["system"]["id"], t["role"]["id"]) for t in consumers}
    preferences = []
    for alias in tasks:
        binding = alias["role"].get("fulfilled_by")
        if (
            binding
            and binding["need_key"] == demand["need_key"]
            and (alias["system"]["id"], binding["role_id"]) in parents
        ):
            preferences.append(context.preference(alias["requirement"]["id"]))
    allowed = {
        i
        for t in consumers
        for i in context.preference(t["requirement"]["id"]).get("reusable_device_ids", [])
    }
    allowed.update(i for p in preferences for i in p.get("reusable_device_ids", []))
    sources = {p["source_id"] for p in preferences if p.get("source_id")}
    if len(sources) > 1:
        gap = question(
            "accessory_source_conflict",
            demand["id"],
            "source_id",
            "同一配套需求对应的角色指定了不同资料来源，请明确分开需求或统一采用来源",
            recipient="customer",
            evidence=preferences,
        )
        return None, dict(gap, status="conflict")
    return dict(allowed=allowed, source_id=next(iter(sources), "")), None
