from copy import deepcopy

from ...definitions.requirements import active_required_roles
from ..schemas import Requirement
from .context import ordered_candidates
from .devices import bind_role, stable_id
from .locks import locked_split_branch
from .quantities import role_quantity
from .questions import question
from .role_choices import candidate_branches


def prepare_roles(context, *, system_ids=None):
    data, tasks, questions = deepcopy(context.configuration), [], []
    if not data["systems"]:
        questions.append(
            question(
                "system_missing", "project", "systems", "请选择房间与系统版本", recipient="customer"
            )
        )
    for system in data["systems"]:
        if system_ids is not None and system["id"] not in system_ids:
            continue
        package = context.packages.get(system["knowledge_package_id"])
        if not package:
            questions.append(
                question(
                    "published_package_missing",
                    system["id"],
                    "knowledge_package_id",
                    "尚未采用已发布的知识包",
                )
            )
            continue
        if package["system_definition_id"] != system["definition_id"]:
            raise ValueError("知识包与系统版本不一致")
        definition = package["definition"]
        if definition.get("status") == "draft":
            questions.append(
                question(
                    "role_definition_unconfirmed",
                    system["id"],
                    "definition_id",
                    "系统角色必要性及功能分支未确认，不能将未勾选的角色视为可省略",
                )
            )
        required_ids = {r["id"] for r in active_required_roles(definition, system["features"])}
        explicit_ids = {
            r["role_id"] for r in data["requirements"] if r["system_id"] == system["id"]
        }
        for role in definition["roles"]:
            if role["id"] not in required_ids | explicit_ids:
                continue
            if role["feature"] and role["feature"] not in system["features"]:
                continue
            matches = [
                r
                for r in data["requirements"]
                if r["system_id"] == system["id"] and r["role_id"] == role["id"]
            ]
            if not matches:
                matches = [
                    Requirement(
                        id=stable_id("role:" + system["id"] + ":" + role["id"]),
                        system_id=system["id"],
                        role_id=role["id"],
                        role=role["name"],
                    ).model_dump(mode="json")
                ]
                data["requirements"].extend(matches)
            for requirement in matches:
                tasks.append(dict(role=role, requirement=requirement, system=system))
    return data, tasks, questions


def role_branches(context, data, task):
    role, requirement, system = task["role"], task["requirement"], task["system"]
    if role.get("fulfilled_by"):
        # This role is bound after its parent's accessory need has been allocated.
        yield data, [], []
        return
    protected = locked_split_branch(
        data,
        requirement,
        reusable_ids=set(context.preference(requirement["id"]).get("reusable_device_ids", [])),
    )
    if protected is not None:
        yield protected
        return
    quantity, gap, evidence = role_quantity(
        role, system, configuration=data, engine=context.repository.engine
    )
    current = next((d for d in data["devices"] if d["id"] == requirement["device_id"]), None)
    if quantity == 0 and requirement.get("allocations"):
        data = bind_role(data, requirement["id"], None)
    if quantity == 0 and current:
        origin = current.get("generated_origin")
        if origin and not origin["variant_locked"] and not origin["quantity_locked"]:
            data = bind_role(data, requirement["id"], None)
        gap = question(
            "quantity_zero_surplus",
            current["id"],
            "quantity",
            "当前需求计算为零，原设备保留待明确移除或调整；不自动删除采购项",
            recipient="customer",
        )
    if gap or quantity == 0:
        yield (
            data,
            [gap] if gap else [],
            [dict(requirement_id=requirement["id"], quantity=str(quantity), evidence=evidence)],
        )
        return
    explicitly_reusable = current and current["id"] in context.preference(requirement["id"]).get(
        "reusable_device_ids", []
    )
    if (
        current
        and not explicitly_reusable
        and (not current.get("generated_origin") or current["generated_origin"]["variant_locked"])
    ):
        yield locked_role(
            data, current, requirement=requirement, quantity=quantity, evidence=evidence
        )
        return
    items = context.candidates(requirement, system)
    if task.get("candidate_variant_ids"):
        items = [i for i in items if i["variant"]["id"] in task["candidate_variant_ids"]]
    choices, ranking_gap, ranking = ordered_candidates(
        context, items, requirement=requirement, system=system
    )
    if not choices:
        gap = question(
            "candidate_conflict" if items else "candidate_missing",
            requirement["id"],
            "candidate",
            "当前候选与明确条件冲突" if items else "已知资料中没有候选，不能据此判定业务无解",
            evidence=[
                dict(variant_id=i["variant"]["id"], status=i["status"], evidence=i["evidence"])
                for i in items
            ],
        )
        gap["status"] = "conflict" if items else "unknown"
        yield data, [gap], []
        return
    yield from candidate_branches(
        context,
        data,
        task=task,
        quantity=quantity,
        evidence=evidence,
        choices=choices,
        ranking_gap=ranking_gap,
        ranking=ranking,
    )


def locked_role(data, current, *, requirement, quantity, evidence):
    questions = []
    if str(quantity) != str(current["quantity"]):
        questions.append(
            question(
                "manual_quantity_preserved",
                current["id"],
                "quantity",
                f"需求数量为 {quantity}，保留人工设备数量 {current['quantity']}",
                recipient="customer",
            )
        )
    return (
        data,
        questions,
        [
            dict(
                requirement_id=requirement["id"],
                device_id=current["id"],
                reason="保留人工选择",
                evidence=evidence,
            )
        ],
    )
