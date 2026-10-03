"""Lazy depth-first composition. Full business checks reject downstream conflicts."""

from copy import deepcopy

from presales.rules.calculation import digest

from ..projections.comparison import configuration_diff
from ..schemas import Configuration
from ..services.manual_edits import marked
from .accessories import accessory_branches
from .devices import stable_id
from .pricing import quote_plan
from .questions import check_questions, question, unique_questions
from .roles import prepare_roles, role_branches


def generate_options(context, *, prices):
    data, tasks, initial_questions = prepare_roles(context)
    data = reset_generated_allocations(data)
    partial = None
    seen = set()
    yielded = False
    for configured, questions, decisions in walk_roles(context, data, tasks, index=0):
        for proposed, gaps, accessory_decisions in accessory_branches(
            context, configured, tasks=tasks
        ):
            yield_options = completed_options(
                context,
                proposed,
                tasks=tasks,
                prices=prices,
                questions=[*initial_questions, *questions, *gaps],
                decisions=[*decisions, *accessory_decisions],
            )
            for option in yield_options:
                signature = digest([option["configuration"], option["questions"]])
                if signature in seen:
                    continue
                seen.add(signature)
                if option["status"] == "conflict":
                    partial = partial or option
                    continue
                yielded = True
                yield option
    if not seen:
        checked = context.repository.check(Configuration.model_validate(data))
        yield proposal_option(context, checked, questions=initial_questions, decisions=[])
    elif partial and not yielded:
        # A rejected branch is evidence of local conflicts, never proof of global infeasibility.
        yield partial


def completed_options(context, proposed, *, tasks, prices, questions, decisions):
    from .combinations import combination_branches

    for configuration, gaps, choices in combination_branches(context, proposed, tasks=tasks):
        checked = context.repository.check(Configuration.model_validate(configuration))
        checked = quote_plan(checked, prices)
        yield proposal_option(
            context, checked, questions=[*questions, *gaps], decisions=[*decisions, *choices]
        )


def walk_roles(context, data, tasks, *, index):
    if index == len(tasks):
        yield data, [], []
        return
    for branch, questions, decisions in role_branches(context, data, tasks[index]):
        for result, later_questions, later_decisions in walk_roles(
            context, branch, tasks, index=index + 1
        ):
            yield result, [*questions, *later_questions], [*decisions, *later_decisions]


def reset_generated_allocations(data):
    result = deepcopy(data)
    result["accessory_allocations"] = [
        a
        for a in data["accessory_allocations"]
        if marked(data, "accessory_allocations", a["id"])
        or a["id"] != stable_id("allocation:" + a["demand_id"] + ":" + a["device_id"])
    ]
    result["included_allocations"] = [
        a
        for a in data["included_allocations"]
        if marked(data, "included_allocations", a["id"])
        or a["id"]
        != stable_id(
            "included:" + a["demand_id"] + ":" + a["device_id"] + ":" + a["included_item_id"]
        )
    ]
    return result


def proposal_option(context, checked, *, questions, decisions):
    data = checked["configuration"]
    questions = [*questions, *check_questions(checked)]
    if not data.get("quotation"):
        questions.append(
            question(
                "quotation_missing",
                "project",
                "quotation",
                "尚未确定报价信息与价格列",
                recipient="customer",
            )
        )
    from ..role_allocations import device_ids

    used = {identity for r in data["requirements"] for identity in device_ids(r)} | {
        a["device_id"] for a in data["accessory_allocations"]
    }
    removals = [
        d["id"] for d in data["devices"] if d.get("generated_origin") and d["id"] not in used
    ]
    for identity in removals:
        questions.append(
            question(
                "generated_surplus",
                identity,
                "remove_device_ids",
                "原生成设备已无用途，采用时可明确移除",
                recipient="customer",
            )
        )
    questions = unique_questions(questions)
    conflicts = any(q.get("status") == "conflict" for q in questions)
    status = "conflict" if conflicts else "partial" if questions else "pass"
    identity = digest([context.proposal_id, data, questions])
    return dict(
        id=identity,
        status=status,
        standard=not any(q["code"] == "recommendation_missing" for q in questions),
        configuration=data,
        checked=checked,
        questions=questions,
        decisions=decisions,
        removal_candidates=removals,
        changes=configuration_diff(context.configuration, data),
    )
