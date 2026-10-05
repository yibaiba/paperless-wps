"""Plan one local business step, not a Cartesian product of complete solutions."""

from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal

from ..projections.comparison import configuration_diff
from ..schemas import Configuration
from .accessories import accessory_options, apply_included, demand_gap, manual_allocation_gap
from .context import PlanningContext
from .devices import put_device
from .fulfillment import bind_fulfilled_roles, fulfillment_devices
from .input_resolution import matches_query, resolve_input
from .quantities import role_quantity
from .roles import locked_role, prepare_roles, role_branches
from .typed_intent import product_terms, typed_dependency, typed_task


def existing_device_ids(configuration):
    return {
        a["device_id"]
        for a in configuration["supply_allocations"]
        if a["source"] == "existing" and Decimal(a["quantity"]) > 0
    }


@dataclass
class NextEditContext(PlanningContext):
    allowed_sources: dict | None = None
    query: str = ""
    selected_variant_id: str = ""
    selected_source_id: str = ""
    system_id: str = ""
    exact_variant_ids: frozenset[str] = field(init=False, default=frozenset())
    input_resolution: dict | None = field(init=False, default=None)

    def __post_init__(self):
        super().__post_init__()
        self.input_resolution = resolve_input(
            self.variants.values(),
            query=self.query,
            allowed_sources=self.allowed_sources or {},
            selected_variant_id=self.selected_variant_id,
            selected_source_id=self.selected_source_id,
        )
        self.variants = {key: self.scoped_variant(value) for key, value in self.variants.items()}
        if self.selected_variant_id:
            self.variants = {
                key: value
                for key, value in self.variants.items()
                if key == self.selected_variant_id
            }
        if self.query:
            resolved_ids = set(self.input_resolution["variant_ids"])
            self.variants = {
                key: value for key, value in self.variants.items() if key in resolved_ids
            }
            self.exact_variant_ids = frozenset(
                key
                for key, value in self.variants.items()
                if self.query.strip().casefold() in {t.casefold() for t in product_terms(value)}
            )

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

    def candidate_catalog(self):
        # Only suitability search is narrowed. The repository still retains the
        # complete fixed catalog for accessory, shared-use and project checks.
        return CandidateCatalog(tuple(v for v in self.variants.values() if self.matches(v)))

    def matches(self, variant):
        if self.exact_variant_ids and variant["id"] not in self.exact_variant_ids:
            return False
        if self.selected_variant_id and variant["id"] != self.selected_variant_id:
            return False
        if not self.scoped_variant(variant)["source_ids"]:
            return False
        return matches_query(variant, self.query)

    def preference(self, requirement_id):
        preference = super().preference(requirement_id)
        existing = existing_device_ids(self.configuration)
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


@dataclass(frozen=True)
class CandidateCatalog:
    items: tuple

    def variants(self):
        return list(self.items)


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


def next_edit_options(
    context, checked, *, system_id, requirement_id=None, recent_requirement_id=None
):
    data, tasks, questions = scoped_roles(context)
    tasks = [t for t in tasks if t["system"]["id"] == system_id]
    priority = requirement_id or recent_requirement_id
    tasks.sort(key=lambda t: t["requirement"]["id"] != priority)
    if context.query:
        options, issues = typed_step(
            context, data, tasks=tasks, checked=checked, requirement_id=requirement_id
        )
        return options, [*questions, *issues]
    recent = next((t for t in tasks if t["requirement"]["id"] == priority), None)
    if recent and (
        recent["requirement"].get("device_id") or recent["requirement"].get("allocations")
    ):
        changes, gaps = role_steps(context, data, recent)
        if changes or gaps:
            return changes, [*questions, *gaps]
    demand = next_demand(checked, tasks=tasks, priority=priority)
    if demand:
        options, gaps = demand_step(context, data, demand=demand, checked=checked, tasks=tasks)
        return options, [*questions, *gaps]
    for task in tasks:
        changed, gaps = role_steps(context, data, task)
        if changed:
            return changed, questions
        questions.extend(gaps)
    return [], questions


def typed_step(context, data, *, tasks, checked, requirement_id):
    selected, issues = typed_task(context, tasks, requirement_id=requirement_id)
    if selected is None:
        return [], issues
    if selected["role"].get("fulfilled_by"):
        return [
            make_option(context, result, gaps=gaps, evidence=[evidence])
            for result, gaps, evidence in typed_dependency(
                context, data, task=selected, tasks=tasks, checked=checked
            )
        ], []
    return list(typed_options(context, data, selected)), []


def next_demand(checked, *, tasks, priority):
    scoped = {t["requirement"]["id"] for t in tasks}
    demands = sorted(
        checked["suggestions"],
        key=lambda d: priority not in d.get("consumer_requirement_ids", []),
    )
    for demand in demands:
        if not scoped.intersection(demand.get("consumer_requirement_ids", [])):
            continue
        if not demand.get("selected"):
            continue
        if demand["status"] != "pass" or Decimal(demand["missing"] or "0") > 0:
            return demand
    return None


def demand_step(context, data, *, demand, checked, tasks):
    if demand["status"] != "pass":
        return [], [demand_gap(data, demand, checked["suggestions"])]
    gap = manual_allocation_gap(data, demand)
    if gap:
        return [], [gap]
    included = apply_included(data, demand)
    if included != data:
        return [make_option(context, included, gaps=[], evidence=[demand["explanation"]])], []
    options = [
        make_option(context, result, gaps=gaps, evidence=[decision])
        for result, gaps, decision in accessory_options(
            context, data, demand=demand, checked=checked, tasks=tasks
        )
    ]
    if options:
        return options, []
    return [], [
        dict(
            code="accessory_candidate_missing",
            message="必要配套没有可采用的配置或来源",
            demand_id=demand["id"],
        )
    ]


def role_steps(context, data, task):
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
    return changed, [q for option in options for q in option["questions"]]


def role_options(context, data, task):
    requirement = task["requirement"]
    current = next((d for d in data["devices"] if d["id"] == requirement["device_id"]), None)
    if current:
        quantity, gap, evidence = role_quantity(
            task["role"], task["system"], configuration=data, engine=context.repository.engine
        )
        if not gap and current["id"] in existing_device_ids(data):
            # Required seats do not change confirmed physical stock or its manual assignment.
            result, gaps, reasons = locked_role(
                data, current, requirement=requirement, quantity=quantity, evidence=evidence
            )
            yield make_option(context, result, gaps=gaps, evidence=reasons)
            return
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
            yield make_option(
                context,
                data,
                gaps=[
                    dict(
                        code="typed_conflict"
                        if choice["status"] == "conflict"
                        else "typed_evidence_required",
                        requirement_id=requirement["id"],
                        variant_id=variant["id"],
                        status=choice["status"],
                        evidence=choice["evidence"],
                        message="匹配产品的适用性检查未通过，请确认部署及兼容依据",
                    )
                ],
                evidence=choice["evidence"],
            )
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
        checked["configuration"], tasks=tasks, demands=checked["suggestions"], context=context
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
