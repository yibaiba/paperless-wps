"""Plan one local business step, not a Cartesian product of complete solutions."""

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal

from ..projections.comparison import configuration_diff
from ..schemas import Configuration
from .accessories import accessory_options, apply_included, manual_allocation_gap
from .context import PlanningContext
from .devices import put_device
from .fulfillment import bind_fulfilled_roles, fulfillment_devices
from .quantities import role_quantity
from .roles import prepare_roles, role_branches


@dataclass
class NextEditContext(PlanningContext):
    allowed_sources: dict | None = None
    query: str = ""
    selected_variant_id: str = ""
    selected_source_id: str = ""
    system_id: str = ""

    def __post_init__(self):
        super().__post_init__()
        self.variants = {key: self.scoped_variant(value) for key, value in self.variants.items()}
        if self.selected_variant_id:
            self.variants = {
                key: value
                for key, value in self.variants.items()
                if key == self.selected_variant_id
            }

    def scoped_variant(self, variant):
        allowed = (self.allowed_sources or {}).get(variant["id"], [])
        sources = [s for s in variant["source_ids"] if s in allowed]
        if self.selected_source_id:
            sources = [s for s in sources if s == self.selected_source_id]
        return dict(variant, source_ids=sources, source_differences=len(sources) > 1)

    def candidates(self, requirement, system):
        items = super().candidates(requirement, system)
        return [
            dict(item, variant=self.scoped_variant(item["variant"]))
            for item in items
            if self.matches(item["variant"])
        ]

    def matches(self, variant):
        if self.selected_variant_id and variant["id"] != self.selected_variant_id:
            return False
        if not self.scoped_variant(variant)["source_ids"]:
            return False
        text = " ".join([variant["product"]["name"], variant["product"]["model"], variant["name"]])
        return all(token in text.casefold() for token in self.query.casefold().split())

    def preference(self, requirement_id):
        preference = super().preference(requirement_id)
        existing = {
            a["device_id"]
            for a in self.configuration["supply_allocations"]
            if a["source"] == "existing" and Decimal(a["quantity"]) > 0
        }
        reusable = {
            d["id"]
            for d in self.configuration["devices"]
            if d["id"] in existing
            and d["source_id"] in (self.allowed_sources or {}).get(d["variant_id"], [])
        }
        # Preview branches only; shared compatibility/capacity checks decide applicability.
        return dict(
            preference,
            reusable_device_ids=sorted(reusable | set(preference.get("reusable_device_ids", []))),
        )


def scoped_roles(context):
    data, tasks, questions = prepare_roles(context, system_ids={context.system_id})
    original_ids = {r["id"] for r in context.configuration["requirements"]}
    data["requirements"] = [
        r
        for r in data["requirements"]
        if r["system_id"] == context.system_id or r["id"] in original_ids
    ]
    tasks = [t for t in tasks if t["system"]["id"] == context.system_id]
    return data, tasks, questions


def next_edit_options(context, checked, *, system_id, requirement_id=None):
    data, tasks, questions = scoped_roles(context)
    tasks = [t for t in tasks if t["system"]["id"] == system_id]
    tasks.sort(key=lambda t: t["requirement"]["id"] != requirement_id)
    if context.query:
        selected = next((t for t in tasks if t["requirement"]["id"] == requirement_id), None)
        if selected is None:
            return [], [dict(code="role_required", message="请明确当前行的业务角色")]
        return list(typed_options(context, data, selected)), questions
    scoped = {t["requirement"]["id"] for t in tasks}
    demands = sorted(
        checked["suggestions"],
        key=lambda d: requirement_id not in d.get("consumer_requirement_ids", []),
    )
    for demand in demands:
        if not scoped.intersection(demand.get("consumer_requirement_ids", [])):
            continue
        if not demand.get("selected") or demand["status"] != "pass":
            continue
        if Decimal(demand["missing"] or "0") <= 0:
            continue
        gap = manual_allocation_gap(data, demand)
        if gap:
            return [], [*questions, gap]
        included = apply_included(data, demand)
        if included != data:
            return [
                make_option(context, included, gaps=[], evidence=[demand["explanation"]])
            ], questions
        options = [
            make_option(context, result, gaps=gaps, evidence=[decision])
            for result, gaps, decision in accessory_options(
                context, data, demand=demand, checked=checked, tasks=tasks
            )
        ]
        if options:
            return options, questions
    for task in tasks:
        options = list(role_options(context, data, task))
        changed = [
            o
            for o in options
            if any(
                c["kind"] in {"devices", "accessory_allocations", "included_allocations"}
                or (
                    c["kind"] == "requirements"
                    and c["after"]
                    and (c["after"].get("device_id") or c["after"].get("allocations"))
                )
                for c in o["changes"]
            )
        ]
        if changed:
            return changed, questions
        questions.extend(gap for option in options for gap in option["questions"])
    return [], questions


def role_options(context, data, task):
    requirement = task["requirement"]
    current = next((d for d in data["devices"] if d["id"] == requirement["device_id"]), None)
    if current:
        quantity, gap, evidence = role_quantity(
            task["role"], task["system"], configuration=data, engine=context.repository.engine
        )
        locked = (current.get("generated_origin") or {}).get("quantity_locked")
        if not gap and quantity and quantity != Decimal(current["quantity"]) and not locked:
            changed = dict(current, quantity=str(quantity))
            result = put_device(data, changed, context=context)
            yield make_option(context, result, gaps=[], evidence=[evidence])
            return
    for result, gaps, evidence in role_branches(context, data, task):
        yield make_option(context, result, gaps=gaps, evidence=evidence)


def typed_options(context, data, task):
    requirement = task["requirement"]
    current = next((d for d in data["devices"] if d["id"] == requirement["device_id"]), None)
    if current is None:
        yield from role_options(context, data, task)
        return
    preference = context.preference(requirement["id"])
    from .context import select_candidates

    choices = select_candidates(context.candidates(requirement, task["system"]), [preference])
    for choice in choices:
        variant = choice["variant"]
        if choice["status"] != "pass":
            continue
        for source_id in variant["source_ids"]:
            device = dict(
                current,
                variant_id=variant["id"],
                source_id=source_id,
                name=variant["product"]["name"],
                variant_snapshot=None,
                source_snapshot=None,
                origin_suggestion=None,
            )
            result = put_device(data, device, context=context)
            yield make_option(context, result, gaps=[], evidence=choice["evidence"])


def make_option(context, proposed, *, gaps, evidence):
    checked = context.repository.check(Configuration.model_validate(deepcopy(proposed)))
    _, tasks, _ = scoped_roles(context)
    tasks = [
        t
        for t in tasks
        if t["role"].get("fulfilled_by")
        and fulfillment_devices(checked["configuration"], task=t, demands=checked["suggestions"])
    ]
    fulfilled, fulfillment_gaps = bind_fulfilled_roles(
        checked["configuration"], tasks=tasks, demands=checked["suggestions"]
    )
    if fulfilled != checked["configuration"]:
        checked = context.repository.check(Configuration.model_validate(fulfilled))
    return {
        "configuration": checked["configuration"],
        "checked": checked,
        "changes": configuration_diff(context.configuration, checked["configuration"]),
        "questions": [*gaps, *fulfillment_gaps],
        "evidence": evidence,
    }


def removal_option(context, checked, *, device_id):
    from ..services.device_removal import remove_devices

    proposed = remove_devices(context.configuration, {device_id}, demands=checked["suggestions"])
    result = context.repository.check(Configuration.model_validate(proposed))
    return dict(
        configuration=result["configuration"],
        checked=result,
        changes=configuration_diff(context.configuration, result["configuration"]),
        questions=[],
        evidence=[dict(reason="用户明确预览移除此产品及其用途分配", device_id=device_id)],
    )
