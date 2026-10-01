"""Resolve selection requirements only from roles fulfilled by this accessory need."""

from .context import select_candidates
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
    return dict(allowed=allowed, source_id=next(iter(sources), ""), preferences=preferences), None


def accessory_candidates(context, *, demand, preferences):
    candidates = [
        dict(variant=context.variants[i], status="pass", evidence=[])
        for i in demand["rule"]["target_variant_ids"]
        if i in context.variants
        and context.variants[i].get("supply_status", "available") == "available"
    ]
    selected = select_candidates(candidates, preferences)
    if candidates and not selected:
        gap = question(
            "accessory_candidate_conflict",
            demand["id"],
            "candidate",
            "当前配套候选与对应角色明确指定或排除的型号、来源要求冲突，请核对需求",
            recipient="customer",
            evidence=preferences,
        )
        return [], dict(gap, status="conflict")
    return selected, None
