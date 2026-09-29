from copy import deepcopy
from decimal import Decimal

from ...definitions.requirements import active_required_roles
from ..schemas import Requirement
from .context import ordered_candidates
from .devices import bind_role, device_for, put_device, stable_id
from .quantities import role_quantity
from .questions import question


def prepare_roles(context):
    data, tasks, questions = deepcopy(context.configuration), [], []
    if not data["systems"]:
        questions.append(
            question(
                "system_missing", "project", "systems", "请选择房间与系统版本", recipient="customer"
            )
        )
    for system in data["systems"]:
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
        questions.extend(feature_questions(data, definition, system))
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
    quantity, gap, evidence = role_quantity(
        role, system, configuration=data, engine=context.repository.engine
    )
    current = next((d for d in data["devices"] if d["id"] == requirement["device_id"]), None)
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
    if current and (
        not current.get("generated_origin") or current["generated_origin"]["variant_locked"]
    ):
        yield locked_role(
            data, current, requirement=requirement, quantity=quantity, evidence=evidence
        )
        return
    items = context.candidates(requirement, system)
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


def feature_questions(data, definition, system):
    questions = []
    if (
        any(r["feature"] for r in definition["roles"])
        and system["id"] not in data["generation"]["features_confirmed"]
    ):
        questions.append(
            question(
                "features_unknown",
                system["id"],
                "features",
                "请确认需要启用的功能，未填写不等于不需要",
                recipient="customer",
                choices=sorted({r["feature"] for r in definition["roles"] if r["feature"]}),
            )
        )
    return questions


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


def candidate_branches(context, data, *, task, quantity, evidence, choices, ranking_gap, ranking):
    role, requirement = task["role"], task["requirement"]
    preference = context.preference(requirement["id"])
    reused = [
        d
        for d in data["devices"]
        if d["id"] in preference.get("reusable_device_ids", [])
        or (
            context.deployment == "shared"
            and d.get("generated_origin")
            and d["kind"] == "hardware"
            and quantity == 1
            and d["quantity"] == "1"
        )
    ]
    for choice in choices:
        variant = choice["variant"]
        for existing in [d for d in reused if d["variant_id"] == variant["id"]]:
            yield (
                bind_role(data, requirement["id"], existing["id"]),
                [
                    dict(
                        question(
                            "existing_quantity_insufficient",
                            existing["id"],
                            "quantity",
                            f"已有设备数量 {existing['quantity']} 不足需求 {quantity}",
                            recipient="customer",
                        ),
                        status="conflict",
                    )
                ]
                if Decimal(existing["quantity"]) < quantity
                else [],
                [
                    dict(
                        requirement_id=requirement["id"],
                        device_id=existing["id"],
                        reason="明确允许复用",
                        evidence=evidence,
                    )
                ],
            )
        device, gap = device_for(
            context,
            variant,
            key="role:" + requirement["id"],
            quantity=quantity,
            kind=role.get("output_kind", "hardware"),
            source_id=preference.get("source_id", ""),
        )
        if gap:
            yield data, [gap], []
            continue
        result = bind_role(
            put_device(data, device, context=context), requirement["id"], device["id"]
        )
        gaps = [ranking_gap] if ranking_gap else []
        if device["quantity"] != str(quantity):
            gaps.append(
                question(
                    "locked_quantity",
                    device["id"],
                    "quantity",
                    "已锁定数量与计算需求不同",
                    recipient="customer",
                )
            )
        yield (
            result,
            gaps,
            [
                dict(
                    requirement_id=requirement["id"],
                    device_id=device["id"],
                    variant_id=variant["id"],
                    quantity=str(quantity),
                    evidence=evidence,
                    compatibility=choice["evidence"],
                    recommendation=ranking,
                )
            ],
        )
