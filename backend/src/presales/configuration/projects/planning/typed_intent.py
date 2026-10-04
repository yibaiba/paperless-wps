"""Resolve typed product intent using only pinned, scoped suitability results."""

from decimal import Decimal

from .accessories import accessory_options, demand_gap
from .input_resolution import product_terms as product_terms
from .input_resolution import unresolved_input


def explicit_task(context, tasks, requirement_id):
    selected = next((t for t in tasks if t["requirement"]["id"] == requirement_id), None)
    if not selected:
        return None, [dict(code="role_required", message="当前行角色不在当前系统有效需求内")]
    if not context.candidates(selected["requirement"], selected["system"]):
        return None, [unresolved_input(context.input_resolution, task=selected)]
    return selected, []


def typed_task(context, tasks, *, requirement_id):
    if requirement_id:
        return explicit_task(context, tasks, requirement_id)
    matches, rejected = [], []
    for task in tasks:
        candidates = context.candidates(task["requirement"], task["system"])
        if any(c["status"] != "conflict" for c in candidates):
            matches.append(task)
        elif candidates:
            rejected.extend(candidates)
    if len(matches) == 1:
        return matches[0], []
    if not matches:
        if rejected:
            return None, [
                dict(
                    code="typed_conflict",
                    message="匹配产品与当前业务条件冲突",
                    evidence=[c["evidence"] for c in rejected],
                )
            ]
        return None, [unresolved_input(context.input_resolution)]
    return None, [
        dict(
            code="role_ambiguous",
            message="输入产品可用于多个角色，请明确当前行用途",
            choices=[
                dict(
                    requirement_id=t["requirement"]["id"],
                    role_id=t["role"]["id"],
                    name=t["role"]["name"],
                )
                for t in matches
            ],
        )
    ]


def typed_dependency(context, data, *, task, tasks, checked):
    relation = task["role"]["fulfilled_by"]
    parents = {t["requirement"]["id"] for t in tasks if t["role"]["id"] == relation["role_id"]}
    for demand in checked["suggestions"]:
        if demand["need_key"] != relation["need_key"] or not parents.intersection(
            demand.get("consumer_requirement_ids", [])
        ):
            continue
        if demand["status"] != "pass":
            yield data, [demand_gap(data, demand, checked["suggestions"])], {}
        elif Decimal(demand["missing"] or "0") > 0:
            yield from accessory_options(context, data, demand=demand, checked=checked, tasks=tasks)
        return
    yield (
        data,
        [
            dict(
                code="dependent_role_required",
                requirement_id=task["requirement"]["id"],
                message="该角色由配套需求满足，请先确认关联主产品及其配套",
            )
        ],
        {},
    )
