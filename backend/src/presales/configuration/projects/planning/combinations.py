"""Expand confirmed combination needs through existing role/accessory branches."""

from copy import deepcopy

from ..calculation.combinations import role_definition
from ..schemas import Configuration, Requirement
from .accessories import accessory_branches
from .devices import stable_id
from .questions import question
from .roles import role_branches


def combination_branches(context, data, *, tasks, processed=frozenset()):
    if not any(
        r["kind"] == "combination" and r["status"] != "disabled"
        for r in data.get("knowledge_snapshot", [])
    ) and not any(
        r["kind"] == "combination" for p in context.packages.values() for r in p["rules"]
    ):
        yield data, [], []
        return
    checked = context.repository.check(Configuration.model_validate(data))
    pending = next(
        (
            c
            for c in checked["checks"]
            if c["kind"] == "combination"
            and c["code"] != "combination_exclude"
            and c["status"] != "pass"
            and (c["rule_id"], c["scope_id"]) not in processed
            and any(
                ((c["rule_id"], c["scope_id"]), g["target"]["id"]) not in processed
                and g["state"] != "pass"
                for g in c["groups"]
            )
        ),
        None,
    )
    if pending is None:
        yield checked["configuration"], [], []
        return
    rule = next(
        r
        for r in checked["configuration"]["knowledge_snapshot"]
        if r["id"] == pending["rule_id"] and r["revision"] == pending["rule_revision"]
    )
    key = (pending["rule_id"], pending["scope_id"])
    next_processed = processed | {key}
    if not pending["generation_enabled"]:
        yield from combination_branches(context, data, tasks=tasks, processed=next_processed)
        return
    groups = [
        g
        for g in pending["groups"]
        if g["state"] != "pass" and (key, g["target"]["id"]) not in processed
    ]
    alternatives = groups if rule["combination"]["mode"] == "require_any" else groups[:1]
    if not alternatives:
        yield data, [], []
        return
    for group in alternatives:
        for branch, gaps, decisions, expanded_tasks in group_branches(
            context, data, group=group, tasks=tasks
        ):
            marker = (key, group["target"]["id"])
            following = processed | {marker}
            if len(alternatives) > 1:
                gaps = [
                    *gaps,
                    question(
                        "recommendation_missing",
                        pending["rule_id"],
                        "combination.targets",
                        "多个必选分支可满足条件，尚未确认分支推荐顺序",
                    ),
                ]
            for result, later_gaps, later_decisions in combination_branches(
                context, branch, tasks=expanded_tasks, processed=following
            ):
                yield result, [*gaps, *later_gaps], [*decisions, *later_decisions]


def group_branches(context, data, *, group, tasks):
    if group["target"]["need_key"]:
        yield from need_branches(context, data, group=group, tasks=tasks)
        return
    target = group["target"]
    systems = [s for s in data["systems"] if s["id"] in group["system_ids"]]
    if not systems or not target["role_id"]:
        yield data, [], [], tasks
        return
    yield from role_group(context, data, group=group, tasks=tasks, systems=systems)


def role_group(context, data, *, group, tasks, systems):
    if not systems:
        yield data, [], [], tasks
        return
    system, *rest = systems
    package = context.packages.get(system.get("knowledge_package_id"))
    if not package:
        yield (
            data,
            [
                question(
                    "published_package_missing",
                    system["id"],
                    "knowledge_package_id",
                    "组合目标缺少已发布知识包",
                )
            ],
            [],
            tasks,
        )
        return
    definitions = dict(packages=list(context.packages.values()), definitions=[])
    role = role_definition(system, group["target"]["role_id"], definitions)
    if not role.get("name") or (role.get("feature") and role["feature"] not in system["features"]):
        yield (
            data,
            [
                question(
                    "combination_role_unavailable",
                    system["id"],
                    "features",
                    "必选目标角色未定义或所需功能未启用",
                )
            ],
            [],
            tasks,
        )
        return
    branch = deepcopy(data)
    requirement = next(
        (
            r
            for r in branch["requirements"]
            if r["system_id"] == system["id"] and r.get("role_id") == role["id"]
        ),
        None,
    )
    if requirement is None:
        requirement = Requirement(
            id=stable_id("role:" + system["id"] + ":" + role["id"]),
            system_id=system["id"],
            role_id=role["id"],
            role=role["name"],
        ).model_dump(mode="json")
        branch["requirements"].append(requirement)
    task = dict(
        role=role,
        requirement=requirement,
        system=system,
        candidate_variant_ids=group["target"]["variant_ids"],
    )
    expanded = [t for t in tasks if t["requirement"]["id"] != requirement["id"]] + [task]
    for selected, gaps, decisions in role_branches(context, branch, task):
        for completed, more_gaps, more_decisions in accessory_branches(
            context, selected, tasks=expanded
        ):
            for result, later_gaps, later_decisions, later_tasks in role_group(
                context, completed, group=group, tasks=expanded, systems=rest
            ):
                yield (
                    result,
                    [*gaps, *more_gaps, *later_gaps],
                    [*decisions, *more_decisions, *later_decisions],
                    later_tasks,
                )


def need_branches(context, data, *, group, tasks):
    if not group["demand_ids"]:
        yield data, [], [], tasks
        return
    choices = {c["demand_id"]: c for c in data["accessory_choices"]}
    if any(
        identity in choices and not choices[identity]["selected"]
        for identity in group["demand_ids"]
    ):
        yield (
            data,
            [
                question(
                    "combination_choice_conflict",
                    group["target"]["id"],
                    "accessory_choices",
                    "必选组合与人工取消配套冲突，请明确选用",
                )
            ],
            [],
            tasks,
        )
        return
    branch = deepcopy(data)
    for identity in group["demand_ids"]:
        choices[identity] = dict(demand_id=identity, selected=True, note="已确认组合要求")
    branch["accessory_choices"] = list(choices.values())
    for result, gaps, decisions in accessory_branches(context, branch, tasks=tasks):
        yield result, gaps, decisions, tasks
