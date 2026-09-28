"""Project inputs and pinned role checks projected into existing resource evaluation."""

from decimal import Decimal, InvalidOperation


def role_profile(system, requirement, definitions):
    package = next(
        (p for p in definitions["packages"] if p["id"] == system.get("knowledge_package_id")), None
    )
    definition = (
        package["definition"]
        if package
        else next(
            (d for d in definitions["definitions"] if d["id"] == system.get("definition_id")), {}
        )
    )
    role = next(
        (r for r in definition.get("roles", []) if r["id"] == requirement.get("role_id")), {}
    )
    reference = role.get("inspection_profile")
    if not reference:
        return None
    profile = next(
        (
            p
            for p in definition.get("inspection_profiles", [])
            if p["id"] == reference["id"] and p["revision"] == reference["revision"]
        ),
        None,
    )
    if profile is None:
        raise ValueError("系统定义缺少已引用的用途检查修订，请核对资料快照")
    return profile


def effective_environment(system, requirement):
    inputs = {a["key"]: dict(a, purpose="project_input") for a in system.get("inputs", [])}
    conflicts = []
    for parameter in requirement.get("environment", []):
        previous = inputs.get(parameter["key"])
        if previous and (previous["value"], previous["unit"]) != (
            parameter["value"],
            parameter["unit"],
        ):
            conflicts.append(parameter["key"])
        inputs[parameter["key"]] = parameter
    return list(inputs.values()), conflicts


def prepare_inspections(data, definitions):
    systems = {s["id"]: s for s in data["systems"]}
    requirements, checks, policies = [], [], {}
    for original in data["requirements"]:
        system = systems[original["system_id"]]
        environment, conflicts = effective_environment(system, original)
        requirement = dict(
            original, environment=environment, resources=list(original.get("resources", []))
        )
        for key in conflicts:
            checks.append(
                input_issue(
                    requirement,
                    key,
                    "系统输入与角色输入不一致，请明确本次采用值",
                    status="conflict",
                )
            )
        profile = role_profile(system, requirement, definitions)
        if profile:
            apply_profile(requirement, profile, checks=checks, policies=policies)
        requirements.append(requirement)
    return dict(data, requirements=requirements), checks, policies


def input_issue(requirement, key, message, *, status="unknown", profile=None):
    return dict(
        kind="project_input",
        status=status,
        requirement_id=requirement["id"],
        system_id=requirement["system_id"],
        input_key=key,
        message=message,
        profile_id=profile["id"] if profile else None,
        profile_revision=profile["revision"] if profile else None,
    )


def apply_profile(requirement, profile, *, checks, policies):
    if profile["status"] != "confirmed":
        checks.append(
            dict(
                kind="inspection",
                status="unknown",
                requirement_id=requirement["id"],
                system_id=requirement["system_id"],
                profile_id=profile["id"],
                profile_revision=profile["revision"],
                message=f"用途检查「{profile['name']}」尚未确认",
            )
        )
        return
    policies[requirement["id"]] = dict(
        selected=profile["selected_device_policy"],
        needs={m["target_need_key"] for m in profile["metrics"] if m["applies_to"] == "accessory"},
    )
    environment = {a["key"]: a for a in requirement["environment"]}
    for metric in profile["metrics"]:
        value, error = metric_input(metric, environment.get(metric["input_key"]))
        if error:
            checks.append(input_issue(requirement, metric["input_key"], error, profile=profile))
            continue
        identity = (metric["key"], metric["applies_to"], metric["target_need_key"])
        if any(
            (r["key"], r.get("applies_to", "selected_device"), r.get("target_need_key", ""))
            == identity
            for r in requirement["resources"]
        ):
            checks.append(
                input_issue(
                    requirement,
                    metric["input_key"],
                    f"{metric['label']}同时有手工需求和用途检查，请移除重复定义",
                    status="conflict",
                    profile=profile,
                )
            )
            continue
        requirement["resources"].append(
            dict(
                key=metric["key"],
                unit=metric["unit"],
                amount=str(value * Decimal(metric["factor"])),
                applies_to=metric["applies_to"],
                target_need_key=metric["target_need_key"],
                aggregation=metric["aggregation"],
                capacity_basis=metric["capacity_basis"],
                inspection_evidence=dict(
                    id=profile["id"],
                    revision=profile["revision"],
                    name=profile["name"],
                    evidence=profile["evidence"],
                    input_key=metric["input_key"],
                    input=str(value),
                    factor=metric["factor"],
                    unit=metric["unit"],
                ),
            )
        )


def metric_input(metric, parameter):
    label = metric["input_label"]
    if parameter is None or parameter["value"] is None:
        return None, f"请填写项目需求：{label}（{metric['input_unit']}）"
    if parameter["kind"] not in {"number", "quantity"} or parameter["unit"] != metric["input_unit"]:
        return None, f"{label}需要数值且单位为{metric['input_unit']}，请核对输入单位"
    try:
        value = Decimal(str(parameter["value"]))
    except InvalidOperation:
        return None, f"{label}不是有效数值"
    if not value.is_finite() or value < 0:
        return None, f"{label}必须是非负有限数值"
    return value, None
