from copy import deepcopy
from decimal import Decimal
from itertools import chain

from ..schemas import Configuration
from ..services.manual_edits import marked
from .accessory_choices import locked_accessory, new_accessory, reusable_accessory_options
from .accessory_preferences import accessory_selection
from .context import ordered_candidates
from .cycles import dependency_cycle
from .devices import stable_id
from .fulfillment import bind_fulfilled_roles
from .questions import question


def accessory_branches(context, data, *, tasks, processed=frozenset(), path=()):
    checked = context.repository.check(Configuration.model_validate(data))
    data = checked["configuration"]
    demand = next(
        (
            s
            for s in checked["suggestions"]
            if s["selected"]
            and s["id"] not in processed
            and (s["status"] != "pass" or Decimal(s["missing"]) > 0)
        ),
        None,
    )
    if demand is None:
        data, gaps = bind_fulfilled_roles(data, tasks=tasks, demands=checked["suggestions"])
        yield data, gaps, []
        return
    next_processed = processed | {demand["id"]}
    gap = (
        demand_gap(data, demand, checked["suggestions"])
        if demand["status"] != "pass"
        else manual_allocation_gap(data, demand)
    )
    if gap:
        for result, gaps, decisions in accessory_branches(
            context, data, tasks=tasks, processed=next_processed, path=path
        ):
            yield result, [gap, *gaps], decisions
        return
    included = apply_included(data, demand)
    if included != data:
        yield from accessory_branches(
            context, included, tasks=tasks, processed=processed, path=path
        )
        return
    options = accessory_options(context, data, demand=demand, checked=checked, tasks=tasks)
    first = next(options, None)
    if first is None:
        gap = question(
            "accessory_candidate_missing",
            demand["id"],
            "target_variant_ids",
            "配套候选缺少可采用的配置或来源",
        )
        for result, gaps, decisions in accessory_branches(
            context, data, tasks=tasks, processed=next_processed, path=path
        ):
            yield result, [gap, *gaps], decisions
        return
    for option, gaps, decision in chain([first], options):
        cycle = dependency_cycle(option, demand, decision.get("device_id"), checked["suggestions"])
        if cycle:
            gap = question(
                "accessory_cycle",
                demand["id"],
                "dependencies",
                "配套形成循环：" + " → ".join(cycle),
                evidence=[dict(path=cycle)],
            )
            gap["status"] = "conflict"
            yield data, [gap], [decision]
            continue
        for result, later_gaps, decisions in accessory_branches(
            context, option, tasks=tasks, processed=next_processed, path=path
        ):
            yield result, [*gaps, *later_gaps], [decision, *decisions]


def accessory_options(context, data, *, demand, checked, tasks):
    task = next(
        (t for t in tasks if t["requirement"]["id"] in demand["consumer_requirement_ids"]), None
    )
    if task is None:
        return
    locked = locked_accessory(context, data, demand)
    if locked:
        yield locked
        return
    selection, preference_gap = accessory_selection(context, tasks=tasks, demand=demand)
    if preference_gap:
        yield data, [preference_gap], dict(demand_id=demand["id"])
        return
    candidates = [
        dict(variant=context.variants[i], status="pass", evidence=[])
        for i in demand["rule"]["target_variant_ids"]
        if i in context.variants
        and context.variants[i].get("supply_status", "available") == "available"
        and (
            not selection["source_id"]
            or selection["source_id"] in context.variants[i]["source_ids"]
        )
    ]
    choices, gap, ranking = ordered_candidates(
        context,
        candidates,
        requirement=task["requirement"],
        system=task["system"],
        need_key=demand["need_key"],
    )
    needed = Decimal(demand["missing"])
    for choice in choices:
        variant = choice["variant"]
        yield from reusable_accessory_options(
            context,
            data,
            variant=variant,
            demand=demand,
            demands=checked["suggestions"],
            **selection,
            gaps=[gap] if gap else [],
            ranking=ranking,
        )
        yield new_accessory(
            context,
            data,
            variant=variant,
            demand=demand,
            needed=needed,
            source_id=selection["source_id"],
            gaps=[gap] if gap else [],
            ranking=ranking,
        )


def apply_included(data, demand):
    result = deepcopy(data)
    remaining = Decimal(demand["missing"])
    for offer in demand.get("included_offers", []):
        if offer["status"] != "pass" or remaining <= 0:
            continue
        amount = min(remaining, Decimal(offer["available"]))
        if amount <= 0:
            continue
        identity = stable_id(
            "included:" + demand["id"] + ":" + offer["device_id"] + ":" + offer["included_item_id"]
        )
        old = next((a for a in result["included_allocations"] if a["id"] == identity), None)
        value = dict(
            id=identity,
            demand_id=demand["id"],
            quantity=str(amount + Decimal(old["quantity"] if old else "0")),
            **{
                k: offer[k]
                for k in (
                    "device_id",
                    "included_item_id",
                    "host_variant_id",
                    "host_variant_revision",
                    "evidence",
                )
            },
        )
        result["included_allocations"] = [
            a for a in result["included_allocations"] if a["id"] != identity
        ] + [value]
        remaining -= amount
    return result


def demand_gap(data, demand, demands):
    gap = question(
        "accessory_basis_missing",
        demand["id"],
        "quantity_basis",
        "；".join(demand["missing_information"]) or "配套条件未通过",
        evidence=[demand["explanation"]],
    )
    gap["status"] = demand["status"]
    if any("循环" in message for message in demand["missing_information"]):
        for target in data["devices"]:
            if target["variant_id"] not in demand["rule"]["target_variant_ids"]:
                continue
            cycle = dependency_cycle(data, demand, target["id"], demands)
            if cycle:
                gap.update(
                    code="accessory_cycle",
                    message="配套形成循环：" + " → ".join(cycle),
                    evidence=[dict(path=cycle)],
                )
                break
    return gap


def manual_allocation_gap(data, demand):
    if not any(
        a["demand_id"] == demand["id"] and marked(data, collection, a["id"])
        for collection in ("accessory_allocations", "included_allocations")
        for a in data[collection]
    ):
        return None
    return question(
        "manual_allocation_preserved",
        demand["id"],
        "quantity",
        f"保留人工配套分配，仍缺 {demand['missing']}；请明确补齐或调整分配",
        recipient="customer",
    )
