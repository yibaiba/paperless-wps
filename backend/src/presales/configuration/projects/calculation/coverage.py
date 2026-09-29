from ...knowledge.evaluator import scope_matches


def coverage_check(message, *, code, responsibility, status="unknown", **refs):
    return dict(
        kind="coverage",
        code=code,
        responsibility=responsibility,
        status=status,
        message=message,
        **refs,
    )


def coverage_checks(data, definitions, variants, *, demands=()):
    catalog = {d["id"]: d for d in definitions["definitions"]}
    packages = {p["id"]: p for p in definitions["packages"]}
    checks, resource_policies = [], {}
    for system in data["systems"]:
        package = packages.get(system.get("knowledge_package_id"))
        definition = package["definition"] if package else catalog.get(system.get("definition_id"))
        requirements = [r for r in data["requirements"] if r["system_id"] == system["id"]]
        if not definition or definition["status"] != "confirmed":
            checks.append(
                coverage_check(
                    "系统版本的角色定义尚未确认",
                    code="system_definition_unconfirmed",
                    responsibility="knowledge",
                    system_id=system["id"],
                )
            )
            continue
        checks.extend(required_roles(system, requirements, definition))
        known_roles = {r["id"] for r in definition["roles"]}
        for requirement in requirements:
            if requirement.get("role_id") not in known_roles:
                continue
            variant = variants.get(requirement.get("device_id"))
            if not variant:
                continue
            review = role_coverage(requirement, variant, package)
            if review["explicit_none"] and any(
                d["selected"]
                and requirement["id"] in d["consumer_requirement_ids"]
                and d["rule"]["accessory_type"] == "required"
                for d in demands
            ):
                review["check"].update(
                    status="conflict", message="无需额外配套的结论与必需配套知识冲突"
                )
            checks.append(review["check"])
            resource_policies[requirement["id"]] = review["resources"]
    if not data["systems"]:
        checks.append(
            coverage_check("尚未建立系统需求", code="missing_systems", responsibility="project")
        )
    return checks, resource_policies


def required_roles(system, requirements, definition):
    selected = {r.get("role_id") for r in requirements}
    from ...definitions.requirements import active_required_roles

    roles = active_required_roles(definition, system.get("features", []))
    checks = [
        coverage_check(
            "缺少必要角色：" + r["name"],
            code="missing_required_role",
            responsibility="project",
            system_id=system["id"],
            role_id=r["id"],
            role_name=r["name"],
            feature=r.get("feature", ""),
        )
        for r in roles
        if r["id"] not in selected
    ]
    known = {r["id"] for r in definition["roles"]}
    checks.extend(
        coverage_check(
            "角色尚未关联系统定义",
            code="unbound_role",
            responsibility="project",
            requirement_id=r["id"],
            system_id=system["id"],
        )
        for r in requirements
        if r.get("role_id") not in known
    )
    if not requirements:
        checks.append(
            coverage_check(
                "本系统尚未表达角色需求",
                code="missing_role_requirements",
                responsibility="project",
                system_id=system["id"],
            )
        )
    return checks


def role_coverage(requirement, variant, package):
    reviews = [
        r
        for r in (package or {}).get("coverage", [])
        if r["role_id"] == requirement.get("role_id") and scope_matches(variant, r["selector"])
    ]
    statuses = {r["accessories"] for r in reviews}
    resources = {r["resources"] for r in reviews}
    conflict = {"none", "complete"} <= statuses or {"required", "not_applicable"} <= resources
    complete = bool(reviews) and statuses <= {"none", "complete"} and not conflict
    status = "conflict" if conflict else "pass" if complete else "unknown"
    message = (
        "产品配套核对结论互相矛盾"
        if conflict
        else "本角色所选产品的配套范围已核对"
        if complete
        else "配套知识范围尚未核对完整"
    )
    return dict(
        check=coverage_check(
            message,
            code="accessory_coverage",
            responsibility="knowledge",
            status=status,
            requirement_id=requirement["id"],
            device_id=requirement["device_id"],
            evidence=reviews,
        ),
        resources=next(iter(resources)) if len(resources) == 1 else "unknown",
        explicit_none="none" in statuses,
    )
