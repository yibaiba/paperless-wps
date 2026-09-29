from copy import deepcopy
from decimal import Decimal
from itertools import chain

from ..schemas import Configuration
from .accessory_choices import locked_accessory, new_accessory, reusable_accessory_options
from .context import ordered_candidates
from .cycles import dependency_cycle
from .devices import bind_role, stable_id
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
    if demand["status"] != "pass":
        gap = demand_gap(data, demand, checked["suggestions"])
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
    candidates = [
        dict(variant=context.variants[i], status="pass", evidence=[])
        for i in demand["rule"]["target_variant_ids"]
        if i in context.variants
        and context.variants[i].get("supply_status", "available") == "available"
    ]
    choices, gap, ranking = ordered_candidates(
        context,
        candidates,
        requirement=task["requirement"],
        system=task["system"],
        need_key=demand["need_key"],
    )
    needed = Decimal(demand["missing"])
    allowed = set(context.preference(task["requirement"]["id"]).get("reusable_device_ids", []))
    for alias in tasks:
        binding = alias["role"].get("fulfilled_by")
        if (
            binding
            and binding["role_id"] == task["role"]["id"]
            and alias["system"]["id"] == task["system"]["id"]
        ):
            allowed.update(
                context.preference(alias["requirement"]["id"]).get("reusable_device_ids", [])
            )
    for choice in choices:
        variant = choice["variant"]
        yield from reusable_accessory_options(
            context,
            data,
            variant=variant,
            demand=demand,
            demands=checked["suggestions"],
            allowed=allowed,
            gaps=[gap] if gap else [],
            ranking=ranking,
        )
        yield new_accessory(
            context,
            data,
            variant=variant,
            demand=demand,
            needed=needed,
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


def bind_fulfilled_roles(data, *, tasks, demands):
    gaps = []
    for task in tasks:
        binding = task["role"].get("fulfilled_by")
        if not binding:
            continue
        parent = next(
            (
                r
                for r in data["requirements"]
                if r["system_id"] == task["system"]["id"] and r["role_id"] == binding["role_id"]
            ),
            None,
        )
        matching = {
            d["id"]
            for d in demands
            if d["need_key"] == binding["need_key"]
            and parent
            and parent["id"] in d["consumer_requirement_ids"]
        }
        devices = {
            a["device_id"] for a in data["accessory_allocations"] if a["demand_id"] in matching
        }
        if binding["status"] != "confirmed" or len(devices) != 1:
            gaps.append(
                question(
                    "role_fulfillment_missing",
                    task["requirement"]["id"],
                    "fulfilled_by",
                    "角色与配套的满足依据尚未确认或未形成唯一设备关联",
                    evidence=[binding],
                )
            )
            continue
        identity = next(iter(devices))
        current = next(r for r in data["requirements"] if r["id"] == task["requirement"]["id"])
        old_device = next((d for d in data["devices"] if d["id"] == current["device_id"]), None)
        if (
            old_device
            and not old_device.get("generated_origin")
            and current["device_id"] != identity
        ):
            gaps.append(
                question(
                    "manual_fulfillment_conflict",
                    current["id"],
                    "device_id",
                    "保留人工关联设备；与生成配套关联不一致",
                    recipient="customer",
                )
            )
            continue
        data = bind_role(data, task["requirement"]["id"], identity)
    return data, gaps


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
